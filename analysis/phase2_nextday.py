"""Phase 2 대안 — 하루 늦은 자전거별 기록으로도 쓸모가 있나.

아침마다 '어제 자정까지의 기록' 만 본다고 가정:
  목록 = 자정 시점에 연쇄(서로 다른 사람 헛대여)가 2 이상이고, 그 뒤 정상 이용으로 끊기지 않은 자전거.
  → 오늘 이 자전거를 처음 빌린 사람이 헛걸음할 확률(정밀도), 오늘 이 자전거들에서 나온 헛걸음 수(막을 수 있는 수),
    고장 신고가 아직 없는 자전거의 비율(= 신고만 보는 공단 목록에 없는 자전거).
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from engine.core import Rule, load_seoul, load_faults, mark

RULE = Rule(max_sec=180, max_m=300, alarm_k=2)


def run(ym):
    R = mark(load_seoul(ROOT / "data" / "raw" / f"rent_{ym}.csv"), RULE)
    F = load_faults(ROOT / "data" / "raw" / "fault_2601-2606.csv")
    R["day"] = R["t0"].dt.normalize()
    # 각 대여 뒤의 연쇄 상태 = 이번 대여까지 반영한 연쇄 (다음 사람 입장의 streak)
    b = R["bike"].to_numpy()
    nxt_same = np.r_[b[1:] == b[:-1], False]
    after = np.where(R["dud"].to_numpy() & ~R["retry"].to_numpy(), R["streak"].to_numpy() + 1,
                     np.where(R["dud"].to_numpy(), R["streak"].to_numpy(), 0))
    R["chain_after"] = after
    # 자전거별 하루의 마지막 대여 → 자정 시점 연쇄
    last = R.groupby(["bike", "day"]).tail(1)
    flagged = last[last["chain_after"] >= RULE.alarm_k][["bike", "day", "t1"]]
    # 다음 날 이후 첫 대여
    firsts = R[["bike", "t0", "dud", "day"]]
    Rb = {k: v for k, v in firsts.groupby("bike")}
    fault_t = F.groupby("bike")["t"].apply(lambda s: np.sort(s.to_numpy())).to_dict()
    n_list, n_first_dud, today_duds, unreported = 0, 0, 0, 0
    per_day = {}
    for bike, day, t1 in flagged.itertuples(index=False):
        g = Rb[bike]
        nd = day + pd.Timedelta(days=1)
        later = g[g["t0"] >= nd]
        if later.empty:
            continue
        n_list += 1
        per_day[nd] = per_day.get(nd, 0) + 1
        first_dud = bool(later["dud"].iloc[0])
        n_first_dud += first_dud
        # 오늘 헛걸음 수: 다음 날의 연속 헛대여(정상 이용 전까지)
        dd = later[later["day"] == nd]["dud"].to_numpy()
        k = 0
        while k < len(dd) and dd[k]:
            k += 1
        today_duds += k
        ft = fault_t.get(bike)
        reported = ft is not None and np.any((ft >= np.datetime64(t1) - np.timedelta64(7, "D")) & (ft < np.datetime64(nd)))
        unreported += not reported
    days = len(per_day)
    return {"month": ym, "morning_list_per_day": round(n_list / max(1, days), 1),
            "first_rider_dud_%": round(100 * n_first_dud / max(1, n_list), 1),
            "preventable_today_per_day": round(today_duds / max(1, days), 1),
            "not_yet_reported_%": round(100 * unreported / max(1, n_list), 1)}


if __name__ == "__main__":
    out = [run(ym) for ym in (sys.argv[1:] or ["2601", "2603", "2606"])]
    for o in out:
        print(o, flush=True)
    lines = ["# Phase 2 대안 — 하루 늦은 자전거별 기록 (자동 생성)", "",
             "| 달 | 아침 목록(대/일) | 오늘 첫 대여자가 헛걸음 | 오늘 막을 수 있는 헛걸음(명/일) | 아직 고장 신고 없음 |", "|---|---|---|---|---|"]
    lines += [f"| {o['month']} | {o['morning_list_per_day']} | {o['first_rider_dud_%']}% | {o['preventable_today_per_day']} | {o['not_yet_reported_%']}% |" for o in out]
    (ROOT / "docs" / "phase2_nextday.md").write_text("\n".join(lines) + "\n")
