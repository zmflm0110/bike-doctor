"""아침 목록 — 어제 자정까지의 기록으로 '서로 다른 사람 헛대여 연쇄가 끊기지 않은 자전거' 를 뽑는다.
웹앱 데이터(export_web)와 매일 작업(server/daily_job) 이 같이 쓴다."""
import numpy as np
import pandas as pd

from .core import Rule, mark

RULE = Rule(max_sec=180, max_m=300, alarm_k=2, retry_gap_sec=120)   # 생년·성별 없는 기록이면 2분 안 재대여를 같은 사람으로 (docs/no_who.md)


def morning_lists(R, F=None, rule=RULE, station_name=None, with_truth=True):
    """R: 통일된 대여표(load_*). F: 고장신고(없으면 None). 반환: {'YYYY-MM-DD': [자전거 항목, ...]} (그날 아침 목록)."""
    station_name = station_name or {}
    R = mark(R, rule)
    R["day"] = R["t0"].dt.normalize()
    d, retry, streak = R["dud"].to_numpy(), R["retry"].to_numpy(), R["streak"].to_numpy()
    R["chain_after"] = np.where(d & ~retry, streak + 1, np.where(d, streak, 0))
    last = R.groupby(["bike", "day"]).tail(1)
    flagged = last[last["chain_after"] >= rule.alarm_k]
    fault_t = F.groupby("bike")["t"].apply(lambda s: np.sort(s.to_numpy())).to_dict() if F is not None else {}
    Rb = {k: v for k, v in R[["bike", "t0", "dud"]].groupby("bike")} if with_truth else {}
    days = {}
    for r in flagged.itertuples():
        nd = r.day + pd.Timedelta(days=1)
        ft = fault_t.get(r.bike)
        reported = bool(ft is not None and np.any((ft >= np.datetime64(r.t1) - np.timedelta64(7, "D")) & (ft < np.datetime64(nd))))
        item = {"bike": r.bike, "station": r.st1, "station_name": station_name.get(r.st1, r.st1), "chain": int(r.chain_after),
                "level": "빨강" if r.chain_after >= 3 else "노랑", "last_dud": r.t1.strftime("%m-%d %H:%M"), "reported": reported}
        if with_truth:
            later = Rb[r.bike][Rb[r.bike]["t0"] >= nd]
            item["truth_first_rider_dud"] = bool(later["dud"].iloc[0]) if not later.empty else None
        days.setdefault(nd.strftime("%Y-%m-%d"), []).append(item)
    for items in days.values():
        items.sort(key=lambda x: (-x["chain"], x["station"]))
    return days
