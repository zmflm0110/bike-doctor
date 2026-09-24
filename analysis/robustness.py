"""연속 헛대여가 '같은 사람의 재시도' 때문은 아닌지 — 생년·성별이 같은 연속 헛대여를 빼고 다시 잰다.
그리고 경보가 있었다면 막을 수 있었던 헛걸음 수."""
import numpy as np, pandas as pd

R = pd.read_csv("data/rent_2603.csv", encoding="cp949",
                usecols=["자전거번호", "대여일시", "대여 대여소번호", "반납일시", "반납대여소번호", "이용거리(M)", "생년", "성별"],
                dtype={"대여 대여소번호": str, "반납대여소번호": str, "생년": str, "성별": str})
R.columns = ["bike", "t0", "st0", "t1", "st1", "dist", "born", "sex"]
R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
R = R.dropna(subset=["t1"]).sort_values(["bike", "t0"]).reset_index(drop=True)
R["dud"] = (R["st0"] == R["st1"]) & ((R["t1"] - R["t0"]).dt.total_seconds() <= 120) & (R["dist"].fillna(0) < 200)
who = R["born"].fillna("?") + R["sex"].fillna("?")
same_bike = R["bike"].eq(R["bike"].shift())
same_person = same_bike & who.eq(who.shift()) & (R["born"].notna())
gap_min = (R["t0"] - R["t1"].shift()).dt.total_seconds() / 60

d = R["dud"].values
prev_dud = same_bike & pd.Series(np.r_[False, d[:-1]])
print(f"헛대여 바로 다음 대여가 같은 생년·성별(같은 사람일 수 있음): {100*(same_person & prev_dud).sum()/prev_dud.sum():.1f}%")
print(f"헛대여 뒤 다음 대여까지 시간 중앙값: {gap_min[prev_dud].median():.1f}분")

# 같은 사람일 수 있는 연속은 끊고 연쇄를 다시 센다: '다른 사람' 들만의 연속 헛대여
streak = np.zeros(len(R), dtype=int)
b = R["bike"].values; sp = same_person.values
for i in range(1, len(R)):
    if b[i] == b[i - 1] and d[i - 1]:
        streak[i] = (streak[i - 1] if not sp[i] else streak[i - 1]) + (0 if sp[i] else 1)
    else:
        streak[i] = 0
R["streak_others"] = streak
print("\n직전 '서로 다른 사람' 연속 헛대여 → 이번 사람 헛대여 %  (같은 사람 재시도로 보이는 대여는 제외)")
mask = ~same_person
for k in range(0, 5):
    sel = R[mask & (R["streak_others"] == k)]
    print(f"  {k}: {len(sel):8d}건  {100*sel['dud'].mean():5.1f}%")

# 경보 효과: '서로 다른 두 사람이 연달아 헛대여' 뒤에 빌린 사람들
flag = mask & (R["streak_others"] >= 2)
print(f"\n경보(서로 다른 2명 연속 헛대여) 뒤 대여 {flag.sum()}건 중 헛걸음 {int(R.loc[flag,'dud'].sum())}명 "
      f"= 3월 한 달에 막을 수 있었던 헛걸음 (도시 전체, 하루 {R.loc[flag,'dud'].sum()/31:.0f}명)")
