"""보고서 5-6 의 '두 무리로 갈린다' 가 자전거 한 대에 이름표를 붙일 만큼 되나 — 평균 차이와 한 대 판정은 다르다.

신고 한 건마다 그 전 24시간의 헛대여들을 모아 '빠른 반납(30초 안·50m 안) 비율' 을 보고, 단말기 신고인지 맞히기.
단말기는 신고의 약 2.7% 뿐이라, 빠른 반납이 조금 더 흔한 정도로는 이름표가 대부분 틀릴 수 있다.
"""
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
    D["fast"] = ((D["t1"] - D["t0"]).dt.total_seconds() < 30) & (D["dist_m"] < 50)
    g = {k: v for k, v in D.groupby("bike")}
    lo, hi = R["t0"].min(), R["t0"].max()
    for r in F[(F["t"] >= lo) & (F["t"] <= hi)].itertuples():
        d = g.get(r.bike)
        if d is None:
            continue
        w = d[(d["t1"] < r.t) & (d["t1"] >= r.t - pd.Timedelta(hours=24))]
        if len(w):
            rows.append({"kind": r.kind, "n_dud": len(w), "fast_share": w["fast"].mean()})
X = pd.DataFrame(rows)
X["terminal"] = X["kind"].eq("단말기")


def auroc(score, y):
    r = pd.Series(score).rank().to_numpy()
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


out = ["# 헛대여 모양으로 한 대씩 고장 종류 맞히기 (자동 생성: `python analysis/fault_kind_per_bike.py`)", "",
       "신고 전 24시간 헛대여가 있는 신고만. '빠른 반납' = 30초 안·50m 안.", "",
       "| 신고 전 헛대여 | 신고 수 | 단말기 비율 | 빠른 반납 비율의 AUROC | '모두 빠름' → 단말기 이름표: 맞은 비율 / 잡은 비율 |", "|---|---|---|---|---|"]
for lab, m in (("1번 이상", X["n_dud"] >= 1), ("2번 이상", X["n_dud"] >= 2), ("3번 이상", X["n_dud"] >= 3)):
    S = X[m]
    y = S["terminal"].to_numpy()
    allfast = (S["fast_share"] == 1).to_numpy()
    prec = y[allfast].mean() if allfast.any() else float("nan")
    rec = allfast[y].mean() if y.any() else float("nan")
    out.append(f"| {lab} | {len(S):,} | {100 * y.mean():.1f}% | {auroc(S['fast_share'].to_numpy(), y):.2f} | {100 * prec:.1f}% / {100 * rec:.1f}% |")
    print(out[-1], flush=True)
(ROOT / "docs" / "fault_kind_per_bike.md").write_text("\n".join(out) + "\n")
