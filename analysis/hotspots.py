"""헛대여 연쇄가 어디서 끝나나(= 고장 자전거가 서 있는 대여소) — 정비 동선. 6월 기준."""
import numpy as np, pandas as pd
R = pd.read_csv("data/rent_2606.csv", encoding="cp949",
                usecols=["자전거번호", "대여일시", "대여 대여소번호", "대여 대여소명", "반납일시", "반납대여소번호", "이용거리(M)", "생년", "성별"],
                dtype={"대여 대여소번호": "category", "대여 대여소명": "category", "반납대여소번호": "category", "생년": "category", "성별": "category", "자전거번호": "category"})
R.columns = ["bike", "t0", "st0", "name0", "t1", "st1", "dist", "born", "sex"]
R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
R = R.dropna(subset=["t1"]).sort_values(["bike", "t0"]).reset_index(drop=True)
d = ((R["st0"].astype(str) == R["st1"].astype(str)) & ((R["t1"] - R["t0"]).dt.total_seconds() <= 120) & (R["dist"].fillna(0) < 200)).values
b = R["bike"].astype(str).values
who = (R["born"].astype(str) + R["sex"].astype(str)).values
sb = np.r_[False, b[1:] == b[:-1]]; sp = sb & np.r_[False, who[1:] == who[:-1]] & R["born"].notna().values
streak = np.zeros(len(R), dtype=np.int32)
for i in range(1, len(R)):
    if sb[i] and d[i - 1]:
        streak[i] = streak[i - 1] + (0 if sp[i] else 1)
# 경보가 켜지는 순간 = 서로 다른 2번째 헛대여가 막 끝남 → 그 자전거가 서 있는 대여소
alarm = (streak == 1) & d & ~sp
A = R.loc[alarm, ["st0", "name0", "t1"]]
per_station = A.groupby(["st0", "name0"], observed=True).size().sort_values(ascending=False)
st_total = R.groupby("st0", observed=True).size()
print(f"6월 경보 {alarm.sum():,}건, 경보가 한 번이라도 난 대여소 {per_station.shape[0]:,}곳 / 전체 {st_total.shape[0]:,}곳")
top = per_station.head(15)
print("경보 많은 대여소 TOP15 (경보 수 / 그 대여소 대여 수)")
for (st, nm), n in top.items():
    print(f"  {nm[:22]:<22} {n:4d} / {st_total.get(st, 0):6,}")
cum = per_station.cumsum() / per_station.sum()
for q in (0.25, 0.5):
    print(f"경보의 {int(q*100)}% 가 대여소 {int((cum < q).sum()) + 1}곳에 몰림 ({100*((cum < q).sum()+1)/st_total.shape[0]:.1f}%)")
hours = A["t1"].dt.hour.value_counts().sort_index()
print("시간대별 경보:", " ".join(f"{h}시:{hours.get(h,0)}" for h in range(0, 24, 3)))

# 선착장 경보는 고장인가 초보인가: 경보 뒤 7일 안 그 자전거 고장 신고율
F = pd.read_csv("data/fault_2601-2606.csv", encoding="cp949"); F.columns = ["bike", "t", "kind"]; F["t"] = pd.to_datetime(F["t"])
ft = F.groupby("bike")["t"].apply(lambda s: np.sort(s.values)).to_dict()
def within(bike, t, h):
    ts = ft.get(bike)
    if ts is None: return False
    i = np.searchsorted(ts, np.datetime64(t)); return i < len(ts) and (ts[i] - np.datetime64(t)) <= np.timedelta64(h, "h")
AA = R.loc[alarm, ["bike", "name0", "t1"]].copy()
AA["fault7"] = [within(str(bk), t + pd.Timedelta(minutes=10), 24 * 7) for bk, t in zip(AA["bike"], AA["t1"])]
AA["pier"] = AA["name0"].astype(str).str.contains("선착장")
nxt = pd.Series(d, index=R.index).shift(-1).fillna(False).astype(bool) & pd.Series(sb, index=R.index).shift(-1).fillna(False).astype(bool)
AA["next_dud"] = nxt.loc[AA.index].values
for name, g in AA.groupby("pier"):
    print(f"{'선착장' if name else '그 외':<6} 경보 {len(g):5d}  7일 안 고장 신고 {100*g['fault7'].mean():5.1f}%  다음 사람도 헛대여 {100*g['next_dud'].mean():5.1f}%")
