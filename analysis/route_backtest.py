"""정비 동선 되짚기 — "기사가 이 동선대로 돌았다면 실제로 몇 명의 헛걸음을 막았나" 를 지난 기록으로 잰다.

가정: 구마다 기사 한 명, 오전 9시에 구 한가운데서 출발, 근무 3시간(engine/route.Shift: 차 18km/h·직선×1.3,
대여소 6분 + 자전거 한 대 4분). 들른 대여소의 목록 자전거는 그 자리에서 고친다(수거) → 그 뒤 그날 그 자전거에
다른 사람이 또 빌렸다 바로 반납한 횟수(정상 이용 전까지) = 막은 헛걸음.

비교 (같은 날·같은 구·같은 시간):
  순위 10곳   지금 앱 — 누적 헛걸음 순위 위 10곳을 가장 짧게 도는 순서, 시간 끝나면 멈춤
  가까운 순   출발점에서 가까운 곳부터
  막는 동선   engine/route.plan — 막을 헛걸음 기대값을 시간 안에 최대로 (값 표는 1·3월로 맞춤)
  (상한)      실제로 그날 일어난 헛걸음을 미리 안다면 — 넘을 수 없는 천장

값 표: 목록 자전거 한 대가 그날 낼 헛걸음 수의 평균을 (연쇄 2·3·4+) × (대여소 붐빔 3단계) 로 1·3월에서 재고,
       도착 시각 뒤에 남은 몫은 그 대여소의 지난 7일 시간대별 대여 비율로 나눈다.
"""
import json, pathlib, sys
from collections import defaultdict
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from engine.core import load_seoul, mark
from engine.morning import RULE, morning_lists
from engine import route as RT

RAW = ROOT / "data" / "raw"
ST = {s["id"]: {"id": s["id"], "lat": s["lat"], "lon": s["lon"], "gu": s["gu"], "name": s["name"].strip()}
      for s in json.load(open(ROOT / "web" / "data" / "stations.json"))}
START_MIN, SH = 9 * 60, RT.Shift()
REGION = {g: r for r, gs in {   # 서울 5 권역 — 정비 팀이 여러 구를 같이 맡는 경우
    "도심권": "종로구 중구 용산구", "동북권": "성동구 광진구 동대문구 중랑구 성북구 강북구 도봉구 노원구",
    "서북권": "은평구 서대문구 마포구", "서남권": "양천구 강서구 구로구 금천구 영등포구 동작구 관악구",
    "동남권": "서초구 강남구 송파구 강동구"}.items() for g in gs.split()}


def month(path):
    """한 달: 날마다 목록, 목록 자전거의 그날 헛걸음 시각들, 대여소 시간대별 대여(지난 7일)·하루 평균."""
    R = mark(load_seoul(path), RULE)
    lists = morning_lists(R, None, with_truth=False)
    R["day"] = R["t0"].dt.normalize()
    R["hour"] = R["t0"].dt.hour
    cnt = R.groupby(["st0", "day", "hour"]).size()
    days = sorted(lists)
    flagged = {(b["bike"], pd.Timestamp(d)) for d in days for b in lists[d]}
    sub = R[[(b, d) in flagged for b, d in zip(R["bike"], R["day"])]]
    duds = defaultdict(list)   # (자전거, 날) → 그날 다른 사람 헛걸음 시각(분), 정상 이용 전까지
    for (bike, day), g in sub.groupby(["bike", "day"]):
        for r in g.itertuples():
            if r.retry:
                continue
            if not r.dud:
                break
            duds[(bike, day)].append((r.t0 - day).total_seconds() / 60)
    return lists, duds, cnt


def station_profile(cnt, st, day):
    """지난 7일 이 대여소의 시간대별 대여 수(24칸)와 하루 평균."""
    h = np.zeros(24)
    lo = day - pd.Timedelta(days=7)
    try:
        s = cnt.loc[st]
    except KeyError:
        return h + 1, 0.0
    s = s[(s.index.get_level_values(0) >= lo) & (s.index.get_level_values(0) < day)]
    for (d, hr), v in s.items():
        h[hr] += v
    return h + 0.5, h.sum() / 7   # 0.5: 한 번도 없던 시간대도 0 이 아니게


def share_after(h, minute):
    hr = int(minute // 60)
    if hr >= 24:
        return 0.0
    frac = 1 - (minute % 60) / 60
    return (h[hr] * frac + h[hr + 1:].sum()) / h.sum()


def chain_bucket(c):
    return min(max(c, 2), 4)


def fit_value(months):
    """1·3월: (연쇄, 붐빔 단계) → 목록 자전거 한 대의 그날 헛걸음 평균. 붐빔 단계 경계는 1·3월 대여소 하루 평균의 3분위."""
    rows = []
    for lists, duds, cnt in months:
        for d, items in lists.items():
            day = pd.Timestamp(d)
            if day.day <= 7:
                continue
            for b in items:
                _, busy = station_profile(cnt, b["station"], day)
                rows.append((chain_bucket(b["chain"]), busy, len(duds.get((b["bike"], day), []))))
    T = pd.DataFrame(rows, columns=["k", "busy", "duds"])
    cuts = list(T["busy"].quantile([1 / 3, 2 / 3]))
    T["lvl"] = np.digitize(T["busy"], cuts)
    table = T.groupby(["k", "lvl"])["duds"].mean().to_dict()
    return table, cuts, T


def evaluate(lists, duds, cnt, table, cuts, sh=SH, area="gu"):
    res = defaultdict(list)
    for d, items in sorted(lists.items()):
        day = pd.Timestamp(d)
        if day.day <= 7:
            continue
        by_gu = defaultdict(lambda: defaultdict(list))
        for b in items:
            s = ST.get(b["station"])
            if s:
                by_gu[s["gu"] if area == "gu" else REGION.get(s["gu"], s["gu"])][b["station"]].append(b)
        for gu, groups in by_gu.items():
            if len(groups) < 3:
                continue
            prof = {st: station_profile(cnt, st, day) for st in groups}
            stations = [dict(ST[st], n=len(bs), bikes=bs) for st, bs in groups.items()]
            gs = [s for s in ST.values() if (s["gu"] if area == "gu" else REGION.get(s["gu"], s["gu"])) == gu]
            c = {"lat": np.mean([s["lat"] for s in gs]), "lon": np.mean([s["lon"] for s in gs])}
            start = min(gs, key=lambda s: RT.meters(c, s))   # 구 한가운데 대여소

            def predicted(s, t):
                h, busy = prof[s["id"]]
                lvl = int(np.digitize([busy], cuts)[0])
                return sum(table.get((chain_bucket(b["chain"]), lvl), 0.0) for b in s["bikes"]) * share_after(h, t)

            def actual(s, t):
                return sum(sum(1 for x in duds.get((b["bike"], day), []) if x > t) for b in s["bikes"])

            rank = sorted(stations, key=lambda s: (-sum(b["chain"] for b in s["bikes"]), -s["n"]))[:10]
            plans = {
                "순위 10곳": RT.within(start, RT.shortest_order(start, rank, sh), sh, START_MIN),
                "가까운 순": RT.within(start, RT.shortest_order(start, stations, sh), sh, START_MIN),
                "막는 동선": RT.plan(start, stations, predicted, sh, START_MIN),
                "(상한)": RT.plan(start, stations, actual, sh, START_MIN),
            }
            total_possible = sum(actual(s, START_MIN) for s in stations)
            for name, r in plans.items():
                used, prevented, _ = RT.simulate(start, r, actual, sh, START_MIN)
                res[name].append({"day": d, "gu": gu, "prevented": prevented, "stops": len(r), "bikes": sum(s["n"] for s in r),
                                  "minutes": used, "possible": total_possible, "cands": len(stations)})
    return {k: pd.DataFrame(v) for k, v in res.items()}


def summarize(res):
    base = res["순위 10곳"]["prevented"].sum()
    rows = [{"동선": name, "막은 헛걸음": int(D["prevented"].sum()), "순위 10곳 대비": f"{100 * D['prevented'].sum() / base:.0f}%",
             "들른 대여소(평균)": round(D["stops"].mean(), 1), "쓴 시간(평균 분)": round(D["minutes"].mean())} for name, D in res.items()]
    m = res["막는 동선"].merge(res["순위 10곳"], on=["day", "gu"], suffixes=("_v", "_r"))
    return pd.DataFrame(rows), (m["prevented_v"] > m["prevented_r"]).mean(), (m["prevented_v"] < m["prevented_r"]).mean(), len(m), \
        int(res["순위 10곳"]["possible"].sum()), res["순위 10곳"]["cands"].mean()


def main():
    train = [month(RAW / "rent_2601.csv"), month(RAW / "rent_2603.csv")]
    table, cuts, T = fit_value(train)
    print("값 표(1·3월):", {k: round(v, 2) for k, v in sorted(table.items())}, "붐빔 경계", [round(c, 1) for c in cuts], flush=True)
    lists, duds, cnt = month(RAW / "rent_2606.csv")
    md = ["# 정비 동선 되짚기 — 2026년 6월 (자동 생성: `python analysis/route_backtest.py`)", "",
          __doc__.split("\n", 1)[1].strip(), "",
          "## 값 표 (1·3월로 맞춤) — 목록 자전거 한 대가 그날 낸 헛걸음 평균", "",
          "| 연쇄 | 한산 | 보통 | 붐빔 |", "|---|---|---|---|"] + \
         [f"| {k}{'명+' if k == 4 else '명'} | " + " | ".join(f"{table.get((k, l), 0):.2f}" for l in range(3)) + " |" for k in (2, 3, 4)] + \
         ["", f"붐빔 단계: 대여소 하루 평균 대여 {cuts[0]:.0f}건 미만 / {cuts[1]:.0f}건 미만 / 그 이상", ""]
    for area, minutes, label in (("gu", 180, "구마다 한 명, 3시간"), ("gu", 60, "구마다 한 명, 1시간"),
                                 ("region", 180, "권역(3~8개 구)마다 한 명, 3시간"), ("region", 90, "권역마다 한 명, 1시간 30분")):
        sh = RT.Shift(minutes=minutes)
        Tb, win, lose, n, possible, per_area = summarize(evaluate(lists, duds, cnt, table, cuts, sh, area))
        print(label, Tb.to_dict("records"), f"이김 {win:.0%} 짐 {lose:.0%}", flush=True)
        md += [f"## {label} (9시 출발)", "", Tb.to_markdown(index=False), "",
               f"- 한 번(구역·날)에 목록 대여소 평균 {per_area:.1f}곳 · 9시 뒤 실제로 난 헛걸음 전체 {possible:,}명",
               f"- {n}번 중 막는 동선이 순위 10곳보다 많이 막음 {100 * win:.0f}%, 적게 막음 {100 * lose:.0f}%", ""]
    (ROOT / "docs" / "route_backtest.md").write_text("\n".join(md) + "\n")
    print("→ docs/route_backtest.md")


if __name__ == "__main__":
    main()
