"""헛대여의 모양(걸린 초·움직인 거리)으로 고장 종류를 짐작할 수 있나 — 경보 뒤 24시간 안 신고된 종류별로 비교. (서울 3개월)"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from engine.core import load_seoul, load_faults, mark

F = load_faults(ROOT / "data" / "raw" / "fault_2601-2606.csv")
rows = []
for ym in ("2601", "2603", "2606"):
    R = mark(load_seoul(ROOT / "data" / "raw" / f"rent_{ym}.csv"))
    D = R[R["dud"]].copy()
    D["sec"] = (D["t1"] - D["t0"]).dt.total_seconds()
    ft = F.groupby("bike")
    for bike, g in D.groupby("bike"):
        if bike not in ft.groups:
            continue
        rep = ft.get_group(bike)
        for r in g.itertuples():
            nxt = rep[(rep["t"] > r.t1) & (rep["t"] <= r.t1 + pd.Timedelta(hours=24))]
            if len(nxt):
                rows.append({"kind": nxt.iloc[0]["kind"], "sec": r.sec, "m": r.dist_m})
X = pd.DataFrame(rows)
T = X.groupby("kind").agg(n=("sec", "size"), sec_median=("sec", "median"), m_median=("m", "median"),
                          under_30s=("sec", lambda s: round(100 * (s < 30).mean(), 1)), moved_50m=("m", lambda s: round(100 * (s >= 50).mean(), 1)))
T = T[T["n"] >= 100].sort_values("n", ascending=False)
print(T.to_string())
(ROOT / "docs" / "fault_kind.md").write_text("# 헛대여 모양 × 뒤따른 고장 신고 종류 (서울 2026-01·03·06, 신고 24시간 안)\n\n" + T.to_markdown() + "\n")
