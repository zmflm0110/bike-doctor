"""헛걸음 엔진 — 공개 대여기록에서 '빌리자마자 반납(헛대여)' 연쇄를 찾아 고장 의심 경보를 낸다.

용어
  헛대여   같은 대여소에 max_sec 초 안에, max_m 미터도 안 가고 반납. 사람이 타 보려다 포기한 흔적.
  연쇄     한 자전거에서 헛대여가 다른 대여 없이 이어진 횟수. 같은 사람의 재시도(생년·성별 같음)는 세지 않는다.
  경보     서로 다른 사람의 헛대여가 alarm_k 번 이어진 순간. 그 자전거는 대여소에 '멀쩡한 척' 서 있다.

모든 함수는 통일된 표(자전거별·시간순)를 받는다:
  bike, t0(대여), st0(대여소), t1(반납), st1(반납 대여소), dist_m, who(같은 사람 판정 키, 없으면 NaN)
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Rule:
    max_sec: int = 120        # 헛대여: 이만큼 안에 반납
    max_m: float = 200.0      # 헛대여: 이만큼 덜 움직임
    alarm_k: int = 2          # 서로 다른 사람 연속 헛대여 몇 번에 경보
    same_person: bool = True  # 같은 사람 재시도를 거를지 (who 가 없으면 무시)


def load_seoul(path, nrows=None):
    """서울 열린데이터광장 따릉이 대여이력(OA-15182, cp949)."""
    cols = ["자전거번호", "대여일시", "대여 대여소번호", "반납일시", "반납대여소번호", "이용거리(M)", "생년", "성별"]
    R = pd.read_csv(path, encoding="cp949", usecols=cols, nrows=nrows,
                    dtype={"자전거번호": "category", "대여 대여소번호": str, "반납대여소번호": str, "생년": str, "성별": str})
    R.columns = ["bike", "t0", "st0", "t1", "st1", "dist_m", "born", "sex"]
    R["who"] = np.where(R["born"].notna(), R["born"].astype(str) + R["sex"].fillna("?").astype(str), None)
    return _finish(R.drop(columns=["born", "sex"]))


def load_tashu(path, nrows=None):
    """대전 타슈 대여이력(공공데이터포털 15137219, utf-8). 생년·성별 없음 → 같은 사람 거르기 불가."""
    cols = ["자전거번호", "대여일시", "대여_대여소ID", "반납일시", "반납_대여소ID", "이용거리(km)"]
    R = pd.read_csv(path, encoding="utf-8-sig", usecols=cols, nrows=nrows,
                    dtype={"자전거번호": "category", "대여_대여소ID": str, "반납_대여소ID": str})
    R.columns = ["bike", "t0", "st0", "t1", "st1", "dist_km"]
    R["dist_m"] = pd.to_numeric(R.pop("dist_km"), errors="coerce") * 1000
    R["who"] = None
    return _finish(R)


def _finish(R):
    R["t0"] = pd.to_datetime(R["t0"], errors="coerce")
    R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
    R["dist_m"] = pd.to_numeric(R["dist_m"], errors="coerce").fillna(0.0)
    R = R.dropna(subset=["t0", "t1"])
    R["bike"] = R["bike"].astype(str)
    return R.sort_values(["bike", "t0"], kind="stable").reset_index(drop=True)


def load_faults(path):
    """서울 고장신고(OA-15644, cp949): 자전거번호, 등록일시, 구분."""
    F = pd.read_csv(path, encoding="cp949")
    F.columns = ["bike", "t", "kind"]
    F["t"] = pd.to_datetime(F["t"])
    F["kind"] = F["kind"].astype(str).str.strip()
    return F.drop_duplicates(["bike", "t"]).sort_values("t").reset_index(drop=True)


def mark(R, rule=Rule()):
    """헛대여(dud), 같은 사람 재시도(retry), 직전까지의 서로 다른 사람 연쇄(streak), 경보(alarm) 열을 붙인다."""
    R = R.copy()
    R["dud"] = ((R["st0"] == R["st1"]) & ((R["t1"] - R["t0"]).dt.total_seconds() <= rule.max_sec)
                & (R["dist_m"] < rule.max_m)).to_numpy()
    b = R["bike"].to_numpy()
    same_bike = np.r_[False, b[1:] == b[:-1]]
    who = R["who"].to_numpy(dtype=object)
    retry = np.zeros(len(R), dtype=bool)
    if rule.same_person and pd.notna(who).any():
        prev = np.r_[[None], who[:-1]]
        retry = same_bike & pd.notna(who) & (who == prev)
    d = R["dud"].to_numpy()
    streak = np.zeros(len(R), dtype=np.int32)
    for i in range(1, len(R)):                       # 자전거별 시간순이라 한 번 훑으면 된다
        if same_bike[i] and d[i - 1]:
            streak[i] = streak[i - 1] + (0 if retry[i] else 1)
    R["retry"] = retry
    R["streak"] = streak
    # 경보: 이번 대여가 헛대여라서 연쇄가 alarm_k 에 막 닿은 순간 (반납 시각에 켜짐)
    R["alarm"] = d & ~retry & (streak == rule.alarm_k - 1)
    return R


def next_dud_table(R, max_k=4):
    """직전 서로 다른 사람 연쇄 k → 이번 사람도 헛대여 비율. 같은 사람 재시도 대여는 뺀다."""
    m = ~R["retry"]
    rows = []
    for k in range(max_k + 1):
        sel = m & (R["streak"] == k)
        if sel.sum():
            rows.append({"k": k, "n": int(sel.sum()), "next_dud_%": round(100 * R.loc[sel, "dud"].mean(), 1)})
    return pd.DataFrame(rows)


def prevented(R, rule=Rule()):
    """경보가 켜진 뒤(연쇄 ≥ alarm_k) 빌린 사람 중 또 헛걸음한 수 = 경보가 있었다면 막을 수 있었던 헛걸음."""
    sel = ~R["retry"] & (R["streak"] >= rule.alarm_k)
    days = max(1, R["t0"].dt.normalize().nunique())
    n = int(R.loc[sel, "dud"].sum())
    return {"after_alarm_rentals": int(sel.sum()), "prevented": n, "per_day": round(n / days, 1)}


def lead_time(R, F, window_days=7):
    """고장 신고 전 window 안에 경보가 먼저 있었던 신고의 비율, 경보→신고 시간(시간), 그 사이 헛걸음 수."""
    A = R.loc[R["alarm"], ["bike", "t1"]]
    alarms = A.groupby("bike")["t1"].apply(lambda s: np.sort(s.to_numpy())).to_dict()
    lo, hi = R["t0"].min(), R["t0"].max()
    F = F[(F["t"] >= lo) & (F["t"] <= hi)]
    g = {k: v for k, v in R[["bike", "t0", "dud"]].groupby("bike")}
    leads, victims, n = [], [], 0
    for bk, t in zip(F["bike"], F["t"]):
        n += 1
        al = alarms.get(bk)
        if al is None:
            continue
        t64 = np.datetime64(t)
        prior = al[(al < t64) & (al > t64 - np.timedelta64(window_days, "D"))]
        if len(prior) == 0:
            continue
        leads.append((t64 - prior[0]) / np.timedelta64(1, "h"))
        rb = g[bk]
        victims.append(int(rb.loc[(rb["t0"] > prior[0]) & (rb["t0"] < t), "dud"].sum()))
    L = np.array(leads)
    return {"faults": n, "with_prior_alarm": len(L), "share_%": round(100 * len(L) / max(1, n), 1),
            "lead_h_median": round(float(np.median(L)), 1) if len(L) else None,
            "victims_mean": round(float(np.mean(victims)), 2) if victims else None}
