"""전기차 충전기 헛충전 — 따릉이 헛대여와 같은 생각: 사람들은 충전이 안 되면 신고 없이 옆 충전기로 간다.

환경부 충전기 상태 API(getChargerStatus)는 충전기마다 '마지막 충전 시작(lastTsdt)·종료(lastTedt)' 를 준다.
몇 분마다 모으면 끝난 충전 한 건 = (시작, 종료) 한 쌍이 된다.
  헛충전   시작하고 max_min 분 안에 끝난 충전 (꽂았는데 안 되거나 바로 끊김)
  연쇄     한 충전기에서 헛충전이 정상 충전 없이 이어진 횟수. 서로 gap_min 분 넘게 떨어진 헛충전은 다른 사람으로 본다
           (같은 사람이 바로 다시 꽂아 보는 재시도는 한 번으로).
  경보     연쇄가 alarm_k 에 닿은 순간.
상태 코드: 1 통신이상, 2 충전대기, 3 충전중, 4 운영중지, 5 점검중, 9 상태미확인 — 2 로 떠 있으면 앱엔 '사용 가능'.
"""
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class EvRule:
    max_min: float = 3.0     # 헛충전: 이만큼 안에 끝남
    gap_min: float = 10.0    # 이보다 가까운 헛충전은 같은 사람의 재시도로 봄
    alarm_k: int = 2


def sessions(snapshots):
    """상태 스냅샷(statId, chgerId, lastTsdt, lastTedt, stat, at) → 끝난 충전 목록(충전기, 시작, 종료, 분)."""
    S = snapshots.copy()
    S["lastTsdt"] = pd.to_datetime(S["lastTsdt"], format="%Y%m%d%H%M%S", errors="coerce")
    S["lastTedt"] = pd.to_datetime(S["lastTedt"], format="%Y%m%d%H%M%S", errors="coerce")
    S = S.dropna(subset=["lastTsdt", "lastTedt"])
    S = S[S["lastTedt"] >= S["lastTsdt"]]
    S["charger"] = S["statId"].astype(str) + "-" + S["chgerId"].astype(str)
    X = S.drop_duplicates(["charger", "lastTsdt", "lastTedt"])[["charger", "lastTsdt", "lastTedt"]]
    X = X.rename(columns={"lastTsdt": "start", "lastTedt": "end"}).sort_values(["charger", "start"]).reset_index(drop=True)
    X["minutes"] = (X["end"] - X["start"]).dt.total_seconds() / 60
    return X


def mark_ev(X, rule=EvRule()):
    """헛충전(dud)·재시도(retry)·직전 연쇄(streak)·경보(alarm)."""
    X = X.copy()
    X["dud"] = X["minutes"] <= rule.max_min
    same = X["charger"].eq(X["charger"].shift())
    gap = (X["start"] - X["end"].shift()).dt.total_seconds() / 60
    X["retry"] = same & X["dud"].shift(fill_value=False) & (gap < rule.gap_min)
    streak = [0] * len(X)
    d, r, s = X["dud"].tolist(), X["retry"].tolist(), same.tolist()
    for i in range(1, len(X)):
        if s[i] and d[i - 1]:
            streak[i] = streak[i - 1] + (0 if r[i] else 1)
    X["streak"] = streak
    X["alarm"] = X["dud"] & ~X["retry"] & (X["streak"] == rule.alarm_k - 1)
    return X


def zombie_chargers(X, now, rule=EvRule()):
    """지금 '연쇄가 끊기지 않은' 충전기 = 앱엔 사용 가능인데 사람들이 연달아 실패한 충전기."""
    last = mark_ev(X, rule).groupby("charger").tail(1)
    chain = last["streak"] + (last["dud"] & ~last["retry"]).astype(int)
    out = last.assign(chain=chain)[chain >= rule.alarm_k]
    out = out.assign(hours_since=(pd.Timestamp(now) - out["end"]).dt.total_seconds() / 3600)
    return out[["charger", "chain", "end", "hours_since"]].sort_values("chain", ascending=False)
