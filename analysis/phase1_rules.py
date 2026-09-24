"""Phase 1 — 경보 기준을 1월로만 정하고, 3·6월·대전에서 그대로 시험한다 (미리 본 데이터에 맞추지 않기).

격자: 헛대여 시간 60/120/180초 × 거리 100/200/300m × 경보 연쇄 2/3회.
지표(경보가 켜진 자전거를 다음에 빌린 사람 기준):
  정밀도   다음 사람도 헛걸음한 비율 (= 경보가 맞은 비율)
  헛경보   다음 사람이 정상적으로 탄 비율 (= 1 − 정밀도)
  막은 수  경보 뒤 헛걸음 수 / 일
  경보 수  하루 경보 수 (정비·구조대가 감당할 양)
선택 규칙(1월에서): 정밀도 ≥ 30% 인 것 중 하루 막은 수가 가장 큰 것.
"""
import itertools, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.core import Rule, load_seoul, load_tashu, mark

RAW = ROOT / "data" / "raw"


def metrics(R, rule):
    days = max(1, R["t0"].dt.normalize().nunique())
    after = ~R["retry"] & (R["streak"] >= rule.alarm_k)
    base = ~R["retry"] & (R["streak"] == 0)
    return {"precision_%": round(100 * R.loc[after, "dud"].mean(), 1) if after.any() else float("nan"),
            "base_%": round(100 * R.loc[base, "dud"].mean(), 2),
            "prevented_per_day": round(R.loc[after, "dud"].sum() / days, 1),
            "alarms_per_day": round(R["alarm"].sum() / days, 1)}


def main():
    jan = load_seoul(RAW / "rent_2601.csv")
    rows = []
    for sec, m, k in itertools.product((60, 120, 180), (100, 200, 300), (2, 3)):
        rule = Rule(max_sec=sec, max_m=m, alarm_k=k)
        rows.append({"sec": sec, "m": m, "k": k, **metrics(mark(jan, rule), rule)})
        print(rows[-1], flush=True)
    G = pd.DataFrame(rows)
    ok = G[G["precision_%"] >= 30]
    best = ok.sort_values("prevented_per_day", ascending=False).iloc[0]
    rule = Rule(max_sec=int(best["sec"]), max_m=float(best["m"]), alarm_k=int(best["k"]))
    print(f"\n1월로 고른 규칙: {rule}")
    tests = [("서울 2026-01 (기준 정한 달)", jan), ("서울 2026-03", load_seoul(RAW / "rent_2603.csv")),
             ("서울 2026-06", load_seoul(RAW / "rent_2606.csv")),
             ("대전 2025-05", load_tashu(RAW / "tashu" / "tashu_2505.csv")), ("대전 2025-10", load_tashu(RAW / "tashu" / "tashu_2510.csv"))]
    out = []
    for name, R in tests:
        out.append({"set": name, **metrics(mark(R, rule), rule)})
        print(out[-1], flush=True)
    T = pd.DataFrame(out)
    md = ["# Phase 1 — 경보 기준 (자동 생성: `python analysis/phase1_rules.py`)", "",
          "## 1월 격자 (기준을 정한 데이터)", "", G.to_markdown(index=False), "",
          f"선택 규칙(정밀도 ≥ 30% 중 하루 막은 수 최대): **{rule.max_sec}초 · {rule.max_m:.0f}m · 서로 다른 사람 {rule.alarm_k}연속**", "",
          "## 같은 규칙을 다른 달·다른 도시에 그대로", "", T.to_markdown(index=False), "",
          f"정밀도 범위(서울 시험 달): {T.iloc[1:3]['precision_%'].min()}~{T.iloc[1:3]['precision_%'].max()}% vs 기준 달 {T.iloc[0]['precision_%']}%"]
    (ROOT / "docs" / "phase1.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
