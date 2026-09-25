"""현장 조사 검증 — 사람이 본 자전거 상태(survey.csv)와, 그 시각까지의 대여기록으로 엔진이 낸 판단을 맞춘다.

실시간 서버(server/live.py)가 돌고 있으면 조사한 그날 바로 (최근 7일 창 = data/live.sqlite):
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
    return int(last["streak"] + 1) if (last["dud"] and not last["retry"]) else (int(last["streak"]) if last["dud"] else 0)


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
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    survey = pd.read_csv(sys.argv[1], encoding="utf-8-sig")
    if sys.argv[2] == "live":
        import datetime as dt
        from server import live
        R = live.window(live.db(), dt.datetime.now())
    else:
        R = load_seoul(sys.argv[2])
    S, m = validate(survey, R)
    print(m)
    S.to_csv(ROOT / "docs" / "field_validation_rows.csv", index=False, encoding="utf-8-sig")
    (ROOT / "docs" / "field_validation.md").write_text(to_markdown(S, m))
    print("→ docs/field_validation.md")
