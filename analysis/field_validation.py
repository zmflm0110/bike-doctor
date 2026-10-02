"""현장 조사 검증 — 사람이 본 자전거 상태(survey.csv)와, 그 시각까지의 대여기록으로 엔진이 낸 판단을 맞춘다.

조사한 그날 바로 — 서울 대여이력 API 로 조사 기간과 그 앞 7일을 채워서(data/live.sqlite, 맥 실시간 서버는 꺼져 있어도 됨):
    python server/supabase_export.py                          # 앱에서 모인 조사 기록 → data/survey.csv
    python analysis/field_validation.py data/survey.csv live
그달 대여이력 파일로(보통 다음 달 중순 공개):
    python analysis/field_validation.py data/survey.csv data/raw/rent_2610.csv

엔진 판단 = 본 시각 직전까지 그 자전거의 '서로 다른 사람 헛대여' 연쇄 (2 이상 노랑, 3 이상 빨강)
지표:
  고장 포착률   사람이 고장이라고 본 자전거 중 엔진도 경보였던 비율
  헛경보율      사람이 멀쩡하다고 본 자전거 중 엔진이 경보였던 비율
  경보 적중률   엔진이 경보였던 자전거 중 사람이 고장이라고 본 비율
표본이 작으니(150대쯤) 95% 신뢰구간(윌슨)을 같이 낸다. 결과는 docs/field_validation.md (보고서에 그대로 붙임).
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from engine.core import load_seoul, mark
from engine.morning import RULE


def judge(R, bike, t):
    g = R[(R["bike"] == bike) & (R["t1"] <= t)]
    if g.empty:
        return 0
    last = g.iloc[-1]
    return int(last["streak"] + 1) if last["dud"] else 0   # 앱·DB 와 같은 연쇄 (재시도여도 그 사람까지 — 2026-09-27 고침)


def wilson(k, n, z=1.96):
    """k/n 비율의 95% 신뢰구간(%) — 표본이 작아도 0·100% 에 붙지 않는 윌슨 구간."""
    if not n:
        return None
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(100 * (c - h), 1), round(100 * (c + h), 1)


def validate(survey, R):
    R = mark(R[R["bike"].isin(set(survey["bike"]))], RULE)   # 조사한 자전거만 (연쇄는 자전거마다 따로라 결과 같음, 한 달 400만 건 → 수백 건)
    S = survey.copy()
    S["at"] = pd.to_datetime(S["at"])
    S["broken"] = S["status"] != "멀쩡함"
    S["chain"] = [judge(R, b, t) for b, t in zip(S["bike"], S["at"])]
    S["alarm"] = S["chain"] >= RULE.alarm_k
    rate = lambda m: round(100 * m.mean(), 1) if len(m) else None
    ci = lambda m: wilson(int(m.sum()), len(m))
    fb, fa, ab = S.loc[S["broken"], "alarm"], S.loc[~S["broken"], "alarm"], S.loc[S["alarm"], "broken"]
    return S, {"조사 대수": len(S), "고장으로 본 대수": int(S["broken"].sum()), "경보였던 대수": int(S["alarm"].sum()),
               "고장 포착률 %": rate(fb), "고장 포착률 95%": ci(fb), "헛경보율 %": rate(fa), "헛경보율 95%": ci(fa),
               "경보 적중률 %": rate(ab), "경보 적중률 95%": ci(ab), "평소 고장 비율 %": rate(S["broken"])}


def add_ai(S, R):
    """경보였던 자전거마다 '조사한 그 시각' 의 자체 AI 확률(analysis/snapshot_model.py 목록 모델) — AI 가 높게 본 자전거가 실제로 더 고장이었나.
    R 은 조사 대여소의 다른 대여까지 든 전체 기록(외면 특징). 지난 석 달 학습 자료가 없으면(data/cache/ml) 건너뜀."""
    try:
        from analysis.ml_compare import features
        from analysis.snapshot_model import samples, FEATS6
        from analysis.train_model import model
        hist = pd.concat([samples(ym) for ym in ("2601", "2603", "2606")])
    except Exception as e:   # 월별 파일·캐시가 없는 곳
        print("AI 확률은 건너뜀:", e)
        return S.assign(p_ai=np.nan)
    mdl = model().fit(hist[FEATS6], hist["y"])
    M = mark(R, RULE).reset_index(drop=True)
    F = features(M)
    b = M["bike"].astype(str).to_numpy()
    starts = {k: v["t0"].to_numpy() for k, v in M[["st0", "t0"]].sort_values(["st0", "t0"]).groupby("st0")}
    out = []
    for bike, at, alarm in zip(S["bike"], pd.to_datetime(S["at"]), S["alarm"]):
        idx = np.where((b == bike) & (M["t1"].to_numpy() <= np.datetime64(at)))[0]
        if not alarm or not len(idx):
            out.append(np.nan); continue
        i = idx[-1]
        row = F.iloc[[i]][list(FEATS6[:5])].copy()
        t1 = M["t1"].iloc[i]
        row["age_h"] = (at - t1).total_seconds() / 3600
        ts = starts.get(M["st1"].iloc[i])
        row["shun"] = np.log1p(0 if ts is None else np.searchsorted(ts, np.datetime64(at), "left") - np.searchsorted(ts, np.datetime64(t1), "right"))
        out.append(float(mdl.predict_proba(row[FEATS6])[:, 1][0]))
    return S.assign(p_ai=out)


def to_markdown(S, m):
    """보고서용 요약 — 숫자 옆에 표본 수와 신뢰구간을 꼭 붙인다."""
    f = lambda k: "—" if m[k] is None else f"{m[k]}%"
    c = lambda k: "" if m[k] is None else f" ({m[k][0]}~{m[k][1]}%)"
    days = pd.to_datetime(S["at"]).dt.date
    lines = [f"# 현장 조사 검증 결과", "",
             f"- 기간 {days.min()} ~ {days.max()} ({days.nunique()}일), 대여소 {S['station'].nunique() if 'station' in S else '?'}곳, "
             f"자전거 {m['조사 대수']}대 (사진 {int(S['photo'].notna().sum()) if 'photo' in S else 0}장)",
             f"- 사람이 고장으로 본 것 {m['고장으로 본 대수']}대 (평소 고장 비율 {f('평소 고장 비율 %')}), 엔진 경보였던 것 {m['경보였던 대수']}대", "",
             "| 지표 | 값 (95% 신뢰구간) | 뜻 |", "|---|---|---|",
             f"| 경보 적중률 | {f('경보 적중률 %')}{c('경보 적중률 95%')} | 엔진이 경보인 자전거 중 사람이 봐도 고장 |",
             f"| 고장 포착률 | {f('고장 포착률 %')}{c('고장 포착률 95%')} | 사람이 본 고장 중 엔진이 미리 경보 |",
             f"| 헛경보율 | {f('헛경보율 %')}{c('헛경보율 95%')} | 멀쩡한 자전거인데 경보 |", "",
             "## 상태별", "", "| 사람이 본 상태 | 대수 | 엔진 경보 |", "|---|---|---|"]
    for st, g in S.groupby("status"):
        lines.append(f"| {st} | {len(g)} | {int(g['alarm'].sum())} |")
    lines += ["", "고장 포착률이 낮은 건 자연스럽다: 아무도 안 빌려 본 고장(헛대여 흔적이 아직 없음)은 엔진이 알 수 없다. "
              "핵심은 **경보 적중률**이 평소 고장 비율보다 얼마나 높은가."]
    if "p_ai" in S and S["p_ai"].notna().sum() >= 4:   # 경보 자전거를 AI 확률 중앙값으로 둘로
        A = S[S["p_ai"].notna()]; med = A["p_ai"].median()
        hi, lo = A[A["p_ai"] >= med], A[A["p_ai"] < med]
        lines += ["", "## 자체 AI 가 높게 본 경보 자전거가 실제로 더 고장이었나", "",
                  "| 경보 자전거 | 대수 | AI 확률 평균 | 사람이 본 고장 (95%) |", "|---|---:|---:|---|"]
        for lab, g in ((f"AI 확률 {100 * med:.0f}% 이상", hi), (f"{100 * med:.0f}% 미만", lo)):
            k = int(g["broken"].sum()); ci = wilson(k, len(g))
            lines.append(f"| {lab} | {len(g)} | {100 * g['p_ai'].mean():.0f}% | {100 * k / max(1, len(g)):.0f}% ({ci[0]}~{ci[1]}%) |")
        lines += ["", "AI 확률은 '다음 사람도 바로 반납' 을 맞히도록 배웠고, 사람은 눈에 보이는 고장만 본다 — 두 값의 크기는 다르지만 **순서**가 맞는지 본다."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    survey = pd.read_csv(sys.argv[1], encoding="utf-8-sig")
    if sys.argv[2] == "live":   # 서울 API 로 조사 기간 + 그 앞 7일을 채워서 (맥 실시간 서버가 꺼져 있어도 됨)
        import datetime as dt
        from server import live
        c, now = live.db(), dt.datetime.now()
        start = pd.to_datetime(survey["at"]).min().to_pydatetime() - dt.timedelta(days=live.LOOKBACK_DAYS)
        days = (now - start).days + 1
        print(f"대여 기록 채우는 중: {start:%m-%d} 부터 ({days}일) — 처음이면 몇 분 걸림", flush=True)
        live.backfill(c, now, days=days)
        live.ensure_complete(c, start, now)
        R = live.window(c, now, days=days)
    else:
        R = load_seoul(sys.argv[2])
    S, m = validate(survey, R)
    S = add_ai(S, R)
    print(m)
    S.to_csv(ROOT / "docs" / "field_validation_rows.csv", index=False, encoding="utf-8-sig")
    (ROOT / "docs" / "field_validation.md").write_text(to_markdown(S, m))
    print("→ docs/field_validation.md")
