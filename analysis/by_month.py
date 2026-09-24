"""달마다 같은 지표 — 계절(겨울 1월 / 봄 3월 / 여름 6월)이 바뀌어도 '서로 다른 사람 연속 헛대여' 신호가 버티는가.

    python by_month.py 2601 2603 2606
"""
import sys
import numpy as np, pandas as pd

F_ALL = pd.read_csv("data/fault_2601-2606.csv", encoding="cp949")
F_ALL.columns = ["bike", "t", "kind"]
F_ALL["t"] = pd.to_datetime(F_ALL["t"])


def month(yymm):
    R = pd.read_csv(f"data/rent_{yymm}.csv", encoding="cp949",
                    usecols=["자전거번호", "대여일시", "대여 대여소번호", "반납일시", "반납대여소번호", "이용거리(M)", "생년", "성별"],
                    dtype={"대여 대여소번호": "category", "반납대여소번호": "category", "생년": "category", "성별": "category", "자전거번호": "category"})
    R.columns = ["bike", "t0", "st0", "t1", "st1", "dist", "born", "sex"]
    R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
    R = R.dropna(subset=["t1"]).sort_values(["bike", "t0"]).reset_index(drop=True)
    R["dud"] = (R["st0"].astype(str) == R["st1"].astype(str)) & ((R["t1"] - R["t0"]).dt.total_seconds() <= 120) & (R["dist"].fillna(0) < 200)
    b = R["bike"].astype(str).values; d = R["dud"].values
    who = (R["born"].astype(str) + R["sex"].astype(str)).values
    born_ok = R["born"].notna().values
    same_bike = np.r_[False, b[1:] == b[:-1]]
    same_person = same_bike & np.r_[False, who[1:] == who[:-1]] & born_ok
    streak = np.zeros(len(R), dtype=np.int32)
    for i in range(1, len(R)):
        if same_bike[i] and d[i - 1]:
            streak[i] = streak[i - 1] + (0 if same_person[i] else 1)
    mask = ~same_person
    rows = {k: (int((mask & (streak == k)).sum()), float(d[mask & (streak == k)].mean() * 100)) for k in range(4)}
    flag = mask & (streak >= 2)
    prevent = int(d[flag].sum())
    days = R["t0"].dt.day.max()

    lo, hi = R["t0"].min().normalize(), R["t0"].max().normalize() + pd.Timedelta(days=1)
    F = F_ALL[(F_ALL["t"] >= lo) & (F_ALL["t"] < hi)].drop_duplicates(["bike", "t"])
    ft = F.groupby("bike")["t"].apply(lambda s: np.sort(s.values)).to_dict()

    def within(bike, t, h):
        ts = ft.get(bike)
        if ts is None:
            return False
        i = np.searchsorted(ts, np.datetime64(t))
        return i < len(ts) and (ts[i] - np.datetime64(t)) <= np.timedelta64(h, "h")

    after = R["t1"] + pd.Timedelta(minutes=10)
    idx_d = np.flatnonzero(d)
    idx_n = np.random.default_rng(0).choice(np.flatnonzero(~d), min(200_000, int((~d).sum())), replace=False)
    p_d = np.mean([within(b[i], after.iloc[i], 24) for i in idx_d])
    p_n = np.mean([within(b[i], after.iloc[i], 24) for i in idx_n])
    chain = np.flatnonzero(mask & (streak >= 1) & d)
    unrep = np.mean([not within(b[i], after.iloc[i], 24 * 7) for i in chain])
    print(f"[20{yymm[:2]}-{yymm[2:]}] 대여 {len(R):,}  헛대여 {100*d.mean():.2f}%  고장신고 {len(F):,}")
    print("   직전 서로다른사람 연속 헛대여 → 다음 사람 헛대여: " + "  ".join(f"{k}:{v[1]:.1f}%({v[0]:,})" for k, v in rows.items()))
    print(f"   경보(2명 연속) 뒤 헛걸음 {prevent:,}명 = 하루 {prevent/days:.0f}명 | 헛대여 뒤 24h 신고 {100*p_d:.2f}% vs 보통 {100*p_n:.2f}% ({p_d/p_n:.1f}배)"
          f" | 연쇄 중 7일 무신고 {100*unrep:.1f}%", flush=True)


for m in sys.argv[1:]:
    month(m)
