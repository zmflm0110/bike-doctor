"""경보가 고장 신고보다 얼마나 먼저 울리나 — 신고 전에 경보가 있었던 경우, 경보→신고 시간과 그 사이 헛걸음한 사람 수. (6월)"""
import numpy as np, pandas as pd
R = pd.read_csv("data/rent_2606.csv", encoding="cp949",
                usecols=["자전거번호", "대여일시", "대여 대여소번호", "반납일시", "반납대여소번호", "이용거리(M)", "생년", "성별"],
                dtype={"대여 대여소번호": str, "반납대여소번호": str, "생년": "category", "성별": "category", "자전거번호": "category"})
R.columns = ["bike", "t0", "st0", "t1", "st1", "dist", "born", "sex"]
R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
R = R.dropna(subset=["t1"]).sort_values(["bike", "t0"]).reset_index(drop=True)
d = ((R["st0"] == R["st1"]) & ((R["t1"] - R["t0"]).dt.total_seconds() <= 120) & (R["dist"].fillna(0) < 200)).values
b = R["bike"].astype(str).values; who = (R["born"].astype(str) + R["sex"].astype(str)).values
sb = np.r_[False, b[1:] == b[:-1]]; sp = sb & np.r_[False, who[1:] == who[:-1]] & R["born"].notna().values
streak = np.zeros(len(R), dtype=np.int32)
for i in range(1, len(R)):
    if sb[i] and d[i - 1]:
        streak[i] = streak[i - 1] + (0 if sp[i] else 1)
alarm = (streak == 1) & d & ~sp
F = pd.read_csv("data/fault_2601-2606.csv", encoding="cp949"); F.columns = ["bike", "t", "kind"]; F["t"] = pd.to_datetime(F["t"])
F = F[(F["t"] >= "2026-06-01") & (F["t"] < "2026-07-01")].drop_duplicates(["bike", "t"]).sort_values("t")
first_alarm = R.loc[alarm, ["bike", "t1"]].copy(); first_alarm["bike"] = first_alarm["bike"].astype(str)
by_bike_alarm = first_alarm.groupby("bike")["t1"].apply(lambda s: np.sort(s.values)).to_dict()
Rb = {k: g for k, g in R.assign(bike=R["bike"].astype(str), dud=d).groupby("bike")}
leads, victims, n_rep, with_alarm = [], [], 0, 0
for bk, t in zip(F["bike"], F["t"]):
    n_rep += 1
    al = by_bike_alarm.get(bk)
    if al is None:
        continue
    prior = al[(al < np.datetime64(t)) & (al > np.datetime64(t) - np.timedelta64(7, "D"))]
    if len(prior) == 0:
        continue
    with_alarm += 1
    ta = prior[0]
    leads.append((np.datetime64(t) - ta) / np.timedelta64(1, "h"))
    g = Rb[bk]; w = g[(g["t0"] > ta) & (g["t0"] < t)]
    victims.append(int(w["dud"].sum()))
L, V = np.array(leads), np.array(victims)
print(f"6월 고장 신고 {n_rep:,}건 중 7일 안에 먼저 경보가 울린 것 {with_alarm:,}건 ({100*with_alarm/n_rep:.1f}%)")
print(f"경보 → 신고 시간: 중앙값 {np.median(L):.1f}시간 (25% {np.percentile(L,25):.1f}, 75% {np.percentile(L,75):.1f})")
print(f"그 사이 헛걸음한 사람: 평균 {V.mean():.2f}명, 1명 이상 {100*(V>=1).mean():.1f}%, 합계 {V.sum():,}명")
