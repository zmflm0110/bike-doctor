"""경보 뒤 24시간 동안 그 자전거에 무슨 일이 있었나 — '공단이 매일 모든 자전거를 걸러 내나' 를 대여 기록으로 본다.

    python analysis/after_alarm.py [2606]

경보(서로 다른 두 번째 사람이 바로 반납) 뒤, 다음 '다른 사람'(같은 사람 재시도는 건너뜀)의 대여가
  - 24시간 안에 있고 또 바로 반납 → 고장인 채 계속 대여소에 있음
  - 24시간 안에 있고 정상으로 탐 → 고장이 아니었거나 탈 만했음
  - 24시간 안에 없음 → 수거·대여 막힘(신고) 또는 외면
매일 모든 자전거를 손으로 점검한다면 첫째 경우가 드물어야 한다. 끝까지 보려고 월말 3일 전 경보까지만.
"""
import pathlib, sys
import numpy as np
import pandas as pd
ROOT = pathlib.Path(__file__).resolve().parents[1]


def main(ym="2606"):
    M = pd.read_pickle(ROOT / "data" / "cache" / "ml" / f"M_{ym}.pkl")
    M = M[M["bike"].notna()].sort_values(["bike", "t0"]).reset_index(drop=True)
    b = M["bike"].astype(str).to_numpy(); d = M["dud"].to_numpy(); r = M["retry"].to_numpy()
    t0 = M["t0"].to_numpy(); t1 = M["t1"].to_numpy()
    end = M["t1"].max().normalize() - pd.Timedelta(days=3)
    al = np.flatnonzero(M["alarm"].to_numpy()); al = al[t1[al] < np.datetime64(end)]
    fail = ride = quiet = late24 = late48 = 0
    for i in al:
        j = i + 1
        while j < len(M) and b[j] == b[i] and r[j]:
            j += 1
        if j >= len(M) or b[j] != b[i] or t0[j] - t1[i] > np.timedelta64(24, "h"):
            quiet += 1
        elif d[j]:
            fail += 1
        else:
            ride += 1
        k = i + 1; last = t1[i]                      # 경보 뒤로 이어진 헛대여 줄이 얼마나 갔나
        while k < len(M) and b[k] == b[i] and d[k]:
            last = t1[k]; k += 1
        late24 += last - t1[i] >= np.timedelta64(24, "h"); late48 += last - t1[i] >= np.timedelta64(48, "h")
    n = len(al)
    print(f"{ym} 경보 {n:,}건 — 24시간 안 다음 다른 사람: 또 바로 반납 {fail / n:.1%} · 정상 이용 {ride / n:.1%} · 아무도 안 빌림 {quiet / n:.1%}")
    print(f"경보 뒤 24시간이 지나서도 또 바로 반납 {late24:,}건({late24 / n:.1%}), 48시간 뒤에도 {late48:,}건({late48 / n:.1%})")


if __name__ == "__main__":
    main(*sys.argv[1:])
