"""경보 한 건마다 '다음에 빌린 다른 사람' 도 헛걸음했나 — 실시간 채점(server/live.py score)과 같은 방식으로 월별 파일을 잰다.

보고서의 "경보 정밀도 52~60%" 는 경보가 켜져 있는 동안 빌린 **모든** 사람 기준이라(21명 연속 같은 긴 연쇄가 크게 들어감),
경보 한 건에 한 명씩만 세는 실시간 채점과 비교하려면 이 숫자가 기준이다.
  경보 한 건 기준      경보 뒤 처음 빌린 다른 사람 (경보를 낸 사람이 다시 타고 간 경우도 포함 → 그 뒤 사람은 대개 멀쩡)
  연쇄 유지 기준      연쇄가 이어진 채 빌린 사람만 (next_dud_table 의 k=2)
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.core import load_seoul, mark, next_dud_table
from engine.morning import RULE


def per_alarm(M):
    A = M.loc[M["alarm"], ["bike", "t1"]]
    g = {k: v for k, v in M.groupby("bike")}
    hit = n = 0
    for b, at in zip(A["bike"], A["t1"]):
        x = g[b]
        nxt = x[(x["t0"] > at) & ~x["retry"]]
        if len(nxt):
            n += 1; hit += bool(nxt["dud"].iloc[0])
    return n, hit


if __name__ == "__main__":
    rows = []
    for ym in ("2601", "2603", "2606"):
        M = mark(load_seoul(ROOT / "data" / "raw" / f"rent_{ym}.csv"), RULE)
        n, hit = per_alarm(M)
        k2 = next_dud_table(M).set_index("k").loc[2, "next_dud_%"]
        rows.append({"달": f"20{ym[:2]}-{ym[2:]}", "경보(다음 사람 있음)": n, "경보 한 건 기준 %": round(100 * hit / n, 1), "연쇄 유지 기준 %": k2})
        print(rows[-1], flush=True)
    T = pd.DataFrame(rows)
    (ROOT / "docs" / "per_alarm.md").write_text("# 경보 한 건 기준 정밀도 (자동 생성: `python analysis/per_alarm.py`)\n\n"
        + (__doc__.split("\n", 1)[1]) + "\n" + T.to_markdown(index=False) + "\n")
