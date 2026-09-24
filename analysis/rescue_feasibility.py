"""따릉이 구조대가 성립하나: 경보 자전거가 다음에 빌려지기 전까지, 같은 대여소에서 다른 자전거를 빌린 사람 수 = 확인해 줄 수 있는 구조대원 후보."""
import numpy as np, pandas as pd
R = pd.read_csv("../04-bike-doctor/data/rent_2606.csv", encoding="cp949",
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
alarm_idx = np.flatnonzero((streak == 1) & d & ~sp)
nxt_same = np.r_[b[1:] == b[:-1], False]
# 경보 자전거의 다음 대여 시각 (같은 자전거 다음 줄)
next_t0 = R["t0"].shift(-1).values
by_station = {st: np.sort(g.values) for st, g in R.groupby("st0")["t0"]}
waits, helpers = [], []
for i in alarm_idx:
    if not nxt_same[i]:
        continue
    t_alarm, t_next, st = R["t1"].values[i], next_t0[i], R["st1"].values[i]
    ts = by_station.get(st)
    if ts is None:
        continue
    n = np.searchsorted(ts, t_next) - np.searchsorted(ts, t_alarm)   # 그 사이 같은 대여소에서 빌린 사람(경보 자전거 제외 근사)
    waits.append((t_next - t_alarm) / np.timedelta64(1, "m")); helpers.append(max(0, n - 1))
w, h = np.array(waits), np.array(helpers)
print(f"경보 {len(alarm_idx):,}건 중 다음 대여까지 추적 {len(w):,}건")
print(f"경보 뒤 다음 사람이 빌리기까지: 중앙값 {np.median(w):.0f}분 (25% {np.percentile(w,25):.0f}분, 75% {np.percentile(w,75):.0f}분)")
print(f"그 사이 같은 대여소에서 다른 자전거를 빌린 사람: 중앙값 {np.median(h):.0f}명, 1명 이상인 경우 {100*(h>=1).mean():.1f}%, 3명 이상 {100*(h>=3).mean():.1f}%")
