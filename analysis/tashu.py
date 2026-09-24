"""다른 도시에서도? — 대전 타슈 대여이력으로 '연속 헛대여 → 다음 사람도 헛대여' 재현. (생년·성별 없음 → 같은 사람 거르기 없이, 서울 첫 분석과 같은 규칙으로 비교)"""
import sys
import numpy as np, pandas as pd

for f in sys.argv[1:]:
    R = pd.read_csv(f, encoding="utf-8-sig", usecols=["자전거번호", "대여일시", "대여_대여소ID", "반납일시", "반납_대여소ID", "이용거리(km)"],
                    dtype={"자전거번호": "category", "대여_대여소ID": str, "반납_대여소ID": str})
    R.columns = ["bike", "t0", "st0", "t1", "st1", "km"]
    R["t0"] = pd.to_datetime(R["t0"], errors="coerce"); R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
    R = R.dropna(subset=["t0", "t1"]).sort_values(["bike", "t0"]).reset_index(drop=True)
    d = ((R["st0"] == R["st1"]) & ((R["t1"] - R["t0"]).dt.total_seconds() <= 120) & (pd.to_numeric(R["km"], errors="coerce").fillna(0) < 0.2)).values
    b = R["bike"].astype(str).values
    sb = np.r_[False, b[1:] == b[:-1]]
    streak = np.zeros(len(R), dtype=np.int32)
    for i in range(1, len(R)):
        if sb[i] and d[i - 1]:
            streak[i] = streak[i - 1] + 1
    cells = []
    for k in range(5):
        m = streak == k
        if m.sum() >= 30:
            cells.append(f"{k}:{100*d[m].mean():.1f}%({m.sum():,})")
    prevent = int(d[streak >= 2].sum())
    days = R["t0"].dt.normalize().nunique()
    print(f"[{f.split('/')[-1]}] 대여 {len(R):,}, 자전거 {R['bike'].nunique():,}, 헛대여 {100*d.mean():.2f}%")
    print("   직전 연속 헛대여 → 다음 사람 헛대여: " + "  ".join(cells))
    print(f"   2연속 뒤 헛걸음 {prevent:,}명 (하루 {prevent/days:.0f}명)", flush=True)
