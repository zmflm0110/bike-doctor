"""목록 보장 — "지금 목록 N대 중 다음 사람도 바로 반납할 자전거가 최소 몇 대" 를 90% 로 보장하는 하한 (분할 컨포멀 예측)

    python analysis/list_guarantee.py        # → docs/list_guarantee.md, supabase/model.sql 끝에 붙일 상수 출력

지금 목록 흉내: 날마다 9·13·18시에, 그 시각 전 마지막 대여가 '서로 다른 2명+ 연쇄의 헛대여' 이고 24시간 안인 자전거들.
자전거마다 자체 모델 확률 p (analysis/train_model.py 와 같은 5특징·같은 모델) → 기대 수 μ = Σp, 흩어짐 σ = √Σp(1−p).
정답 = 그 자전거를 다음에 빌린 다른 사람도 바로 반납했나(그 뒤 아무도 안 빌린 자전거는 뺀다).
하한 = μ + q·σ. q 는 **배울 때 안 쓴 달(보정 달)** 의 목록들에서 (실제 − μ)/σ 의 10% 분위 → 시험 달에서 90% 이상 맞는지 확인.
(자전거끼리 독립이 아니라서 정규 근사 q = −1.28 만으로는 모자랄 수 있다 — 그래서 실제 자료로 q 를 맞춘다.)
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from analysis.ml_compare import marked, features, realtime_rows
from analysis.train_model import FEATS5, model

HOURS = (9, 13, 18)


def snapshots(M, F, p):
    """날·시각마다 지금 목록 (자전거별 p, 정답 y)."""
    M = M.reset_index(drop=True)
    b = M["bike"].astype(str).to_numpy(); r = M["retry"].to_numpy(); d = M["dud"].to_numpy()
    ar = np.arange(len(M)).astype(float)
    nxt = pd.Series(np.where(~r, ar, np.nan)).groupby(b).shift(-1).groupby(b).bfill().to_numpy()
    y = np.where(np.isnan(nxt), np.nan, d[np.nan_to_num(nxt).astype(int)])
    T = pd.DataFrame({"bike": b, "t1": M["t1"].to_numpy(), "dud": d, "chain": F["chain"].to_numpy(), "p": p, "y": y})
    out = []
    days = pd.to_datetime(M["t1"]).dt.normalize().unique()
    for day in sorted(days)[7:]:   # 첫 7일은 지난 기록이 모자람
        for h in HOURS:
            at = np.datetime64(pd.Timestamp(day) + pd.Timedelta(hours=h))
            last = T[T["t1"] < at].groupby("bike", sort=False).tail(1)
            L = last[last["dud"] & (last["chain"] >= 2) & (last["t1"] >= at - np.timedelta64(24, "h")) & last["y"].notna()]
            if len(L) >= 10:
                mu, var = L["p"].sum(), (L["p"] * (1 - L["p"])).sum()
                out.append({"at": pd.Timestamp(at), "n": len(L), "mu": mu, "sd": np.sqrt(var), "real": L["y"].sum()})
    S = pd.DataFrame(out)
    S["z"] = (S["real"] - S["mu"]) / S["sd"]
    return S


def month(ym, m):
    M = marked(ym).reset_index(drop=True)
    F = features(M)
    return M, F, m.predict_proba(F[FEATS5])[:, 1]


def main():
    lines = ["# 목록 보장 — 최소 몇 대가 진짜인가 (자동 생성: `python analysis/list_guarantee.py`)", "",
             '> **지난 실험 기록.** 반납 순간 모델(`analysis/train_model.py`)로 목록 보장을 시험했더니 하한이 시험 달에서 40\\~58% 만 맞았다 — 목록 자전거의 확률을 크게 잡았기 때문. 이 결과로 **목록에 맞춘 모델**(`analysis/snapshot_model.py`, 경과 시간·외면 포함)로 바꿨고, 그 모델의 보장은 98\\~100% 맞는다 → [model.md](model.md).', "", __doc__.split("\n", 1)[1].strip(), ""]
    rows = []
    qs = []
    for trm, cal, tem in ((("2601",), "2603", "2606"), (("2603",), "2606", "2601"), (("2606",), "2601", "2603")):
        tr = pd.concat([realtime_rows(marked(x).reset_index(drop=True), features(marked(x).reset_index(drop=True))) for x in trm])
        m = model().fit(tr[FEATS5], tr["y"])
        Sc = snapshots(*month(cal, m))
        q = float(np.quantile(Sc["z"], 0.10))
        St = snapshots(*month(tem, m))
        lo_c = np.floor(St["mu"] + q * St["sd"]); lo_n = np.floor(St["mu"] - 1.2816 * St["sd"])
        rows.append({"배움": trm[0], "보정": cal, "시험": tem, "q(보정 달)": round(q, 2), "시험 목록 수": len(St),
                     "목록 평균 대수": round(St["n"].mean(), 1), "기대 Σp 평균": round(St["mu"].mean(), 1), "실제 평균": round(St["real"].mean(), 1),
                     "하한 평균": round(lo_c.mean(), 1), "하한이 맞은 비율 %": round(100 * (St["real"] >= lo_c).mean(), 1),
                     "(정규근사 −1.28 이면) %": round(100 * (St["real"] >= lo_n).mean(), 1)})
        qs.append(q)
        print(rows[-1], flush=True)
    T = pd.DataFrame(rows)
    q_use = float(min(qs))   # 가장 조심스러운 값
    lines += ["## 시험 (배움·보정·시험 달을 모두 다르게)", "", T.to_markdown(index=False), "",
              f"→ 앱에 쓰는 q = **{q_use:.2f}** (세 조합 중 가장 조심스러운 값). 기대 수는 실제와 맞고(위 '기대' vs '실제'), 하한은 시험 달에서 90% 안팎으로 맞는다.",
              "", "화면: \"지금 목록 N대 중 약 μ대는 다음 사람도 바로 반납할 거예요 — 90% 확률로 최소 ⌊μ + q·σ⌋대\"."]
    (ROOT / "docs" / "list_guarantee.md").write_text("\n".join(lines) + "\n")
    print(f"q_use={q_use:.4f}")


if __name__ == "__main__":
    main()
