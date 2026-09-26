"""전기차 충전기 헛충전 검증 — 모은 상태 기록(data/ev.sqlite)으로 '연쇄가 다음 충전을 예고하나' 를 잰다 → docs/ev_validation.md

따릉이와 같은 질문: 헛충전(3분 안에 끝난 충전) 뒤, 다른 사람의 다음 충전도 헛충전인가? 평소보다 얼마나 자주?

먼저 기록 품질을 거른다 (2026-09-25 첫 6시간에서 찾음):
  - 시작 = 종료 (0초 충전): 어떤 사업자는 충전 중(stat 3)인데도 5분마다 0초 충전을 남긴다 → 고장이 아니라 기록 방식.
  - 사업자 전체가 짧은 충전 10% 이상: 충전기 수백 대가 한꺼번에 고장일 리 없다 → 그 사업자 기록은 따로 본다.
  같은 사람의 재시도(10분 안 다시 헛충전)는 한 번으로 친다(engine/ev.py).

    python analysis/ev_validate.py            # docs/ev_validation.md 갱신
"""
import os, pathlib, sqlite3, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.ev import EvRule, mark_ev

DB = pathlib.Path(os.environ.get("EV_DB", ROOT / "data" / "ev.sqlite"))
OUT = pathlib.Path(os.environ.get("EV_REPORT", ROOT / "docs" / "ev_validation.md"))
ZERO_MAX, SHORT_MAX = 0.01, 0.10   # 사업자 기록 품질 기준: 0초 충전 1% 미만, 짧은 충전 10% 미만
OFF = {"1": "통신이상", "4": "운영중지", "5": "점검중"}


def load(db=DB):
    c = sqlite3.connect(db)
    S = pd.read_sql("select * from snap", c)
    S["t"] = pd.to_datetime(S["at"])
    # 바뀐 것만 저장하므로 '찍은 때' 는 runs 표에서 (없던 예전 기록은 snap 의 at 으로)
    has_runs = c.execute("select count(*) from sqlite_master where name='runs'").fetchone()[0]
    S.attrs["runs"] = pd.to_datetime(pd.read_sql("select at from runs", c)["at"]) if has_runs else pd.Series(dtype="datetime64[ns]")
    for f in ["lastTsdt", "lastTedt"]:
        S[f] = pd.to_datetime(S[f], format="%Y%m%d%H%M%S", errors="coerce")
    S["charger"] = S["statId"] + "-" + S["chgerId"]
    S["op"] = S["statId"].str[:2]   # 충전소 ID 앞 두 글자 = 운영 사업자
    return S


GAP_MAX = pd.Timedelta(minutes=int(os.environ.get("EV_GAP_MAX", "25")))
# 찍은 간격이 이보다 길면(맥이 잠듦·GitHub 이 못 돎) 이어진 구간이 끊긴 것으로 본다. 맥 5분·GitHub 10분(늦으면 15~20분)이라 25분.


def run_times(S):
    """찍은 때들 (runs 표 + 예전 기록의 at)."""
    return pd.concat([S["t"], S.attrs.get("runs", pd.Series(dtype="datetime64[ns]"))]).drop_duplicates().sort_values().reset_index(drop=True)


def segments(S):
    """찍은 때들을 '빈틈없이 이어 찍은 구간' 으로 나눈다 → {찍은 때: 구간 번호}, [(시작, 끝)]."""
    ts = run_times(S)
    seg = (ts.diff() > GAP_MAX).cumsum()
    spans = [(g.iloc[0], g.iloc[-1]) for _, g in ts.groupby(seg)]
    return dict(zip(ts, seg)), spans


def sessions(S):
    """처음 본 때 기준으로 끝난 충전 한 건씩. API 는 충전기마다 '마지막 한 건' 과 최근 10분 안에 바뀐 충전기만 주므로,
    못 찍은 사이(잠듦)에 끝난 충전은 대부분 사라진다 → 각 구간이 시작된 뒤(10분 여유) 끝난 것만 쓰고, 구간 번호(seg)를 붙인다.
    연쇄·다음 충전은 같은 구간 안에서만 잇는다(key = 충전기#구간) — 빈틈을 건너면 사이의 충전이 빠졌을 수 있다."""
    seg_of, spans = segments(S)
    X = S.dropna(subset=["lastTsdt", "lastTedt"]).sort_values("t").drop_duplicates(["charger", "lastTsdt", "lastTedt"]).copy()
    X["seg"] = X["t"].map(seg_of)
    X["seg_start"] = X["seg"].map(lambda k: spans[k][0])
    X = X[(X["lastTedt"] >= X["lastTsdt"]) & (X["lastTedt"] >= X["seg_start"] - pd.Timedelta(minutes=10))]
    X = X.rename(columns={"lastTsdt": "start", "lastTedt": "end"})
    X["key"] = X["charger"] + "#" + X["seg"].astype(str)
    X = X[["charger", "key", "seg", "op", "start", "end"]]
    X["minutes"] = (X["end"] - X["start"]).dt.total_seconds() / 60
    X["zero"] = X["minutes"] == 0
    return X.sort_values(["key", "start"]).reset_index(drop=True)


def op_quality(X, rule=EvRule()):
    q = X.groupby("op").agg(sessions=("minutes", "size"), chargers=("charger", "nunique"), zero=("zero", "mean"),
                            short=("minutes", lambda m: ((m > 0) & (m <= rule.max_min)).mean()))
    q["clean"] = (q["zero"] < ZERO_MAX) & (q["short"] < SHORT_MAX)
    return q.sort_values("sessions", ascending=False)


def persistence(X, rule=EvRule()):
    """연쇄가 k 에 닿은 헛충전 뒤, 같은 사람 재시도를 건너뛴 다음 충전이 또 헛충전인 비율."""
    M = mark_ev(X[~X["zero"]].drop(columns="charger").rename(columns={"key": "charger"}).reset_index(drop=True), rule)
    base = M["dud"].mean()
    out = []
    for k in (1, 2, 3):
        hit = n = 0
        for _, g in M.groupby("charger", sort=False):
            d, r, s = g["dud"].tolist(), g["retry"].tolist(), g["streak"].tolist()
            for i in range(len(g)):
                if d[i] and not r[i] and s[i] == k - 1:
                    j = next((j for j in range(i + 1, len(g)) if not r[j]), None)
                    if j is not None:
                        n += 1; hit += d[j]
        out.append((k, n, hit))
    return base, len(M), out


def offline_after(S, X, rule=EvRule()):
    """연쇄 2 이상이 된 충전기 중, 그 뒤 통신이상·운영중지·점검중으로 바뀐 비율 vs 다른 충전기 (사업자가 알아챘나)."""
    M = mark_ev(X[~X["zero"]].reset_index(drop=True).assign(charger=lambda d: d["key"]), rule)
    M["charger"] = M["charger"].str.split("#").str[0]
    first = M[M["alarm"]].groupby("charger")["end"].min()
    off = S[S["stat"].isin(OFF)].groupby("charger")["t"].agg(list)
    alarmed = sum(any(t > first[c] for t in off.get(c, [])) for c in first.index)
    others = set(X["charger"]) - set(first.index)
    rest = sum(c in off.index for c in others)
    return len(first), alarmed, len(others), rest


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "—"


def main():
    S = load(DB)
    X = sessions(S)
    q = op_quality(X)
    clean = X[X["op"].isin(q.index[q["clean"]])]
    snaps = run_times(S)
    hours = (snaps.max() - snaps.min()).total_seconds() / 3600
    _, spans = segments(S)
    covered = sum((b - a).total_seconds() for a, b in spans) / 3600
    lines = [
        "# 전기차 충전기 헛충전 검증 (중간)",
        "",
        f"`python analysis/ev_validate.py` 로 다시 만든다. 자료: 서울 충전기 상태 {len(snaps)}번 찍음, "
        f"{snaps.min():%m-%d %H:%M} ~ {snaps.max():%m-%d %H:%M} (약 {hours:.0f}시간, 간격 중앙값 {snaps.diff().dt.total_seconds().median() / 60:.0f}분).",
        f"그중 빈틈없이 이어 찍은 구간 {len(spans)}개, 합 {covered:.0f}시간 ({covered / hours if hours else 0:.0%}). 나머지는 맥이 잠들었거나 인터넷이 끊긴 때 — "
        "충전기 API 는 지난 기록을 다시 주지 않아 그 사이 충전은 사라진다. 연쇄는 같은 구간 안에서만 잇는다.",
        "",
        "> **아직 판정 전.** 목표는 1\\~2주, 연쇄 2 뒤 다음 충전 100건 이상. 아래는 쌓이는 대로 바뀐다.",
        "",
        "## 1. 기록 품질 — 고장이 아닌 것부터 뺀다",
        "",
        f"모으기 시작한 뒤 끝난 충전 {len(X):,}건 중 **시작 = 종료(0초)** 가 {pct(X['zero'].sum(), len(X))}. "
        "어떤 사업자는 충전 중(상태 3)으로 떠 있는 동안에도 5분마다 0초 충전을 남긴다 — 고장이 아니라 기록 방식이다.",
        f"그리고 사업자 **전체** 충전의 10% 이상이 3분 안에 끝나는 곳이 있다. 충전기 수백 대가 한꺼번에 고장일 리 없으니 이것도 기록 방식으로 보고 따로 뺀다.",
        "",
        f"기준: 0초 충전 {ZERO_MAX:.0%} 미만 **그리고** 짧은 충전(0초 초과 3분 이하) {SHORT_MAX:.0%} 미만인 사업자만 '기록 정상'. "
        f"→ {q['clean'].sum()}곳 / {len(q)}곳, 충전 {len(clean):,}건 ({pct(len(clean), len(X))}).",
        "",
        "| 뺀 사업자(ID 앞 두 글자) | 충전 | 충전기 | 0초 | 짧은 충전 |",
        "|---|---|---|---|---|",
    ]
    for op, r in q[~q["clean"]].head(12).iterrows():
        lines.append(f"| {op} | {r.sessions:,} | {r.chargers:,} | {r.zero:.1%} | {r.short:.1%} |")
    lines += ["", "## 2. 연쇄는 다음 충전을 예고하나", "",
              "헛충전(0초 초과 3분 이하)이 서로 다른 사람에게서 k번 이어진 뒤(10분 안 재시도는 같은 사람), **다음 충전도 헛충전**인 비율.", "",
              "| 자료 | 평소 헛충전 | 1번 뒤 | 2번 뒤 (경보) | 3번 뒤 |", "|---|---|---|---|---|"]
    for name, sub in [("기록 정상 사업자", clean), ("모든 사업자 (0초만 뺌)", X)]:
        base, n_all, out = persistence(sub)
        cells = [f"{pct(h, n)} ({h}/{n})" for _, n, h in out]
        lines.append(f"| {name} | {base:.1%} ({n_all:,}건) | " + " | ".join(cells) + " |")
    n_a, off_a, n_o, off_o = offline_after(S, clean)
    lines += ["", "## 3. 사업자가 알아챘나 (신고 대신 상태 바뀜)", "",
              f"기록 정상 사업자에서 연쇄 2(경보)가 된 충전기 {n_a}대 중 그 뒤 통신이상·운영중지·점검중으로 바뀐 것 {off_a}대({pct(off_a, n_a)}). "
              f"경보 없던 충전기는 {n_o:,}대 중 {off_o:,}대({pct(off_o, n_o)})가 한 번이라도 그 상태였다.",
              "",
              "## 4. 한계", "",
              "- API 는 충전기마다 **마지막 충전 한 건**만 준다. 헛충전 뒤 5분 안에 누가 다시 꽂으면 앞의 헛충전은 안 보인다. "
              "대부분 같은 사람의 재시도라 연쇄(10분 넘게 떨어진 다른 사람)에는 영향이 작지만, 평소 헛충전 비율은 실제보다 낮게 나올 수 있다.",
              "- 사람을 구분할 정보가 없다. '10분 넘게 떨어진 헛충전 = 다른 사람' 은 가정이다(따릉이는 생년·성별로 확인할 수 있었다).",
              "- 0초·짧은 충전의 뜻은 사업자마다 다르다. 기준(1%·10%)은 첫날 자료로 정했다 — 다른 날에도 같은 사업자가 걸러지는지 본다.",
              "- 정답(실제 고장) 자료가 없다. 상태가 운영중지·점검중으로 바뀌는 것은 사업자가 알아챘다는 간접 증거일 뿐이다.",
              ""]
    OUT.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
