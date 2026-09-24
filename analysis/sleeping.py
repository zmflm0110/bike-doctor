"""잠든 자전거: 반납된 대여소에서 다른 자전거는 계속 빌려 가는데 이 자전거만 오래 안 빌려짐 = 사람들이 보고 피함.
검증: 잠에서 깬 뒤 첫 대여가 헛대여인 비율, 잠든 동안/직후 고장 신고 비율 (6월)."""
import numpy as np, pandas as pd
R = pd.read_csv("data/rent_2606.csv", encoding="cp949", usecols=["자전거번호", "대여일시", "대여 대여소번호", "반납일시", "반납대여소번호", "이용거리(M)"],
                dtype={"대여 대여소번호": str, "반납대여소번호": str, "자전거번호": "category"})
R.columns = ["bike", "t0", "st0", "t1", "st1", "dist"]
R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
R = R.dropna(subset=["t1"]).sort_values(["bike", "t0"]).reset_index(drop=True)
R["dud"] = (R["st0"] == R["st1"]) & ((R["t1"] - R["t0"]).dt.total_seconds() <= 120) & (R["dist"].fillna(0) < 200)
b = R["bike"].astype(str).values
nxt = np.r_[b[1:] == b[:-1], False]
gap_h = (R["t0"].shift(-1) - R["t1"]).dt.total_seconds().values / 3600
st = R["st1"].values
by_st = {s: np.sort(g.values) for s, g in R.groupby("st0")["t0"]}
rows = []
for i in np.flatnonzero(nxt & (gap_h >= 6)):
    ts = by_st.get(st[i])
    if ts is None:
        continue
    others = np.searchsorted(ts, R["t0"].values[i + 1]) - np.searchsorted(ts, R["t1"].values[i])
    rows.append((gap_h[i], others, bool(R["dud"].values[i + 1]), R["st0"].values[i + 1] == st[i]))
G = pd.DataFrame(rows, columns=["gap_h", "others", "wake_dud", "same_st"])
G = G[G["same_st"]]   # 같은 대여소에서 깨어난 것만 (재배치로 옮겨진 경우 제외)
base = R["dud"].mean()
print(f"평소 헛대여 {100*base:.2f}%")
print("잠든 시간 · 그동안 같은 대여소에서 빌려 간 다른 대여 수 → 깨어난 첫 대여가 헛대여일 확률")
for (lo, hi) in [(6, 24), (24, 72), (72, 1e9)]:
    for olo, ohi in [(0, 10), (10, 50), (50, 1e9)]:
        m = (G["gap_h"] >= lo) & (G["gap_h"] < hi) & (G["others"] >= olo) & (G["others"] < ohi)
        if m.sum() >= 30:
            print(f"  {lo:>3}~{'' if hi > 1e8 else int(hi)}시간, 다른 대여 {olo}~{'' if ohi > 1e8 else int(ohi)}건: {m.sum():6,}회  깨어난 첫 대여 헛대여 {100*G.loc[m,'wake_dud'].mean():5.1f}%")
