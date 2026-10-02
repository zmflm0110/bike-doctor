"""자전거 고장인가, 대여소 고장인가 — 한 대여소에서 '다른 자전거들' 이 같이 헛대여를 내면 거치대·단말기 문제일 수 있다.

    python analysis/station_fault.py       # → docs/station_fault.md (서울 1·3·6월)

재는 것
  1) 자전거 경보(서로 다른 2명 연달아)가 울릴 때, 같은 대여소에서 지난 60분 안에 '다른 자전거' 헛대여가 몇 번 있었나(대여소 소란) →
     소란이 클수록 그 자전거의 다음 사람 헛대여가 낮아지나 (= 자전거 탓이 아니었다)
  2) 대여소 경보: 60분 안에 서로 다른 자전거 k대가 그 대여소에서 헛대여 → 다음 60분 그 대여소에서 빌린 사람(아무 자전거)의 헛대여 비율
     vs 그 대여소의 평소 헛대여 비율
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from analysis.ml_compare import marked

W = np.timedelta64(60, "m")


def station_noise(M):
    """헛대여 한 줄마다: 같은 대여소에서 그 반납 전 60분 안에 '다른 자전거' 가 낸 헛대여 수."""
    D = M.loc[M["dud"], ["bike", "st1", "t1"]].copy()
    D["bike"] = D["bike"].astype(str)
    D = D.sort_values(["st1", "t1"]).reset_index()
    out = np.zeros(len(D), dtype=np.int32)
    for st, g in D.groupby("st1").indices.items():
        t = D["t1"].to_numpy()[g]; b = D["bike"].to_numpy()[g]
        lo = np.searchsorted(t, t - W, "left")
        for j, i in enumerate(g):
            seg = b[lo[j]:j]
            out[i] = len(set(seg) - {b[j]})
    return pd.Series(out, index=D["index"])


def next_rider(M):
    """줄마다 다음 '재시도 아닌' 대여가 헛대여였나 (없으면 NaN)."""
    b = M["bike"].astype(str).to_numpy(); r = M["retry"].to_numpy(); d = M["dud"].to_numpy()
    ar = np.arange(len(M)).astype(float)
    nr = pd.Series(np.where(~r, ar, np.nan))
    nxt = nr.groupby(b).shift(-1).groupby(b).bfill().to_numpy()
    return np.where(np.isnan(nxt), np.nan, d[np.nan_to_num(nxt).astype(int)])


def station_alarm(M, k):
    """60분 안에 서로 다른 자전거 k대 이상 헛대여한 대여소·시각(처음 닿은 때) → 다음 60분 그 대여소 대여의 헛대여 비율."""
    D = M.loc[M["dud"], ["bike", "st1", "t1"]].sort_values(["st1", "t1"])
    R = M[["st0", "t0", "dud"]].sort_values(["st0", "t0"])
    rg = {s: (v["t0"].to_numpy(), v["dud"].to_numpy()) for s, v in R.groupby("st0")}
    own = R.groupby("st0")["dud"].mean().to_dict()   # 대여소마다 그달 평소 헛대여 비율
    hits = n = 0; expect = 0.0; cool = {}
    for st, g in D.groupby("st1"):
        t = g["t1"].to_numpy(); b = g["bike"].astype(str).to_numpy()
        lo = np.searchsorted(t, t - W, "left")
        for j in range(len(t)):
            if len(set(b[lo[j]:j + 1])) >= k and (st not in cool or t[j] > cool[st]):
                cool[st] = t[j] + W   # 한 번 울리면 60분 쉼
                if st in rg:
                    tt, dd = rg[st]
                    a, z = np.searchsorted(tt, t[j], "right"), np.searchsorted(tt, t[j] + W, "right")
                    hits += dd[a:z].sum(); n += z - a; expect += (z - a) * own.get(st, 0)
    return n, hits, expect


def main():
    out = ["# 자전거 고장인가, 대여소 고장인가 (자동 생성: `python analysis/station_fault.py`)", "", __doc__.split("\n", 1)[1].strip(), ""]
    rows1, rows2 = [], []
    for ym in ("2601", "2603", "2606"):
        M = marked(ym)
        noise = station_noise(M)
        nx = next_rider(M)
        al = M["alarm"].to_numpy()
        idx = np.where(al & ~np.isnan(nx))[0]
        nz = noise.reindex(idx).fillna(0).to_numpy()
        y = nx[idx]
        for lab, sel in (("0", nz == 0), ("1", nz == 1), ("2", nz == 2), ("3+", nz >= 3)):
            rows1.append({"달": ym, "같은 대여소 다른 자전거 헛대여(60분)": lab, "경보 수": int(sel.sum()), "다음 사람 헛대여 %": round(100 * y[sel].mean(), 1) if sel.any() else None})
        base = 100 * M["dud"].mean()
        for k in (2, 3, 4):
            n, h, e = station_alarm(M, k)
            rows2.append({"달": ym, "서로 다른 자전거": f"{k}대+", "다음 60분 대여": n, "그중 헛대여 %": round(100 * h / max(1, n), 1),
                          "그 대여소들의 평소 %": round(100 * e / max(1, n), 1), "서울 평소 %": round(base, 2)})
        print(ym, rows1[-4:], rows2[-3:], flush=True)
    out += ["## 1. 자전거 경보 — 같은 대여소가 소란하면 자전거 탓이 아닐까", "", pd.DataFrame(rows1).to_markdown(index=False), "",
            "## 2. 대여소 경보 — 여러 자전거가 한꺼번에 헛대여한 대여소", "", pd.DataFrame(rows2).to_markdown(index=False), "",
            "## 결론", "",
            "- 같은 대여소가 소란할 때 울린 자전거 경보는 다음 사람 헛대여가 몇 %p 낮지만(달마다 들쭉날쭉, 경보의 2\\~4% 뿐) 여전히 평소의 10배 넘게 높다 — **고장은 대부분 자전거 탓**이고, 경보에서 빼지 않는다.",
            "- 여러 자전거가 한꺼번에 헛대여한 대여소의 다음 60분은 그 대여소들의 평소보다 조금 높을 뿐이다(위 표) — 대여소 고장 경보는 자전거 경보(평소의 약 14배)보다 훨씬 약해서 **만들지 않는다.**"]
    (ROOT / "docs" / "station_fault.md").write_text("\n".join(out) + "\n")
    print("→ docs/station_fault.md")


if __name__ == "__main__":
    main()
