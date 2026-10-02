"""지금 목록에 맞춘 자체 모델 — '목록에 올라 있는 동안' 의 자전거로 배운다 (반납 순간만 배운 모델은 목록에서 확률을 크게 잡았다)

    python analysis/snapshot_model.py --check      # 시험만 (배움·시험 달을 나눠)
    python analysis/snapshot_model.py              # 세 달로 배워 supabase/model.sql 다시 만듦 + docs/model.md 갱신

목록 흉내: 3시간마다(0·3·…·21시) 그 시각 전 마지막 대여가 '서로 다른 2명+ 연쇄의 헛대여' 이고 24시간 안인 자전거.
특징 7개 = 반납 순간 5개(analysis/train_model.py) + **경과 시간**(마지막 헛대여 뒤 몇 시간) + **외면**(그사이 같은 대여소에서 다른 사람이 빌려 간 수).
정답 = 그 자전거를 다음에 빌린 다른 사람도 바로 반납했나(그 뒤 아무도 안 빌린 자전거는 뺀다).
"""
import argparse, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from analysis.ml_compare import marked, features, boot_diff
from analysis.train_model import FEATS5, model, eval_trees, to_sql

FEATS6 = FEATS5 + ["age_h", "shun"]   # shun = 그사이 같은 대여소에서 다른 사람이 빌려 간 수(log1p) — 계절에 덜 흔들리는 '외면'
STEP = np.timedelta64(3, "h")


def samples(ym):
    """목록 표본: 후보 줄(헛대여, 연쇄 2+)이 다음 대여 전·24시간 안에 걸친 3시간 격자 시각마다 한 줄."""
    return samples_from(marked(ym))


def samples_from(M):
    """samples 와 같음 — 이미 mark() 한 대여표로 (다른 도시·실시간 자료)."""
    M = M.reset_index(drop=True)
    F = features(M)
    b = M["bike"].astype(str).to_numpy(); r = M["retry"].to_numpy(); d = M["dud"].to_numpy()
    t0 = M["t0"].to_numpy(); t1 = M["t1"].to_numpy()
    same_next = np.r_[b[1:] == b[:-1], False]
    nxt_t0 = np.where(same_next, np.r_[t0[1:], t0[:1]], np.datetime64("2100-01-01"))
    ar = np.arange(len(M)).astype(float)
    nxt = pd.Series(np.where(~r, ar, np.nan)).groupby(b).shift(-1).groupby(b).bfill().to_numpy()
    y = np.where(np.isnan(nxt), np.nan, d[np.nan_to_num(nxt).astype(int)])
    cand = np.where(d & (F["chain"].to_numpy() >= 2) & ~np.isnan(y) & (pd.to_datetime(t1).day >= 8))[0]
    base = np.datetime64(pd.Timestamp(t1.min()).normalize())
    end = np.minimum(nxt_t0[cand], t1[cand] + np.timedelta64(24, "h"))
    first = np.ceil((t1[cand] - base) / STEP).astype(int)
    last = np.floor((end - base - np.timedelta64(1, "s")) / STEP).astype(int)
    cnt = np.clip(last - first + 1, 0, None)
    rows = np.repeat(cand, cnt)
    k = np.concatenate([np.arange(c) for c in cnt]) if len(cnt) else np.array([], int)
    T = base + (np.repeat(first, cnt) + k) * STEP
    S = F.iloc[rows][FEATS5].reset_index(drop=True).copy()
    S["age_h"] = ((T - t1[rows]) / np.timedelta64(1, "m") / 60).astype(np.float32)
    S["y"] = y[rows]; S["at"] = T; S["row"] = rows
    st = M["st1"].to_numpy()[rows]
    starts = {k: v["t0"].to_numpy() for k, v in M[["st0", "t0"]].sort_values(["st0", "t0"]).groupby("st0")}
    sh = np.zeros(len(rows))
    for k in np.unique(st):
        ts = starts.get(k)
        if ts is None: continue
        ii = np.where(st == k)[0]
        sh[ii] = np.searchsorted(ts, T[ii], "left") - np.searchsorted(ts, t1[rows][ii], "right")
    S["shun"] = np.log1p(np.clip(sh, 0, None)).astype(np.float32)
    return S


def lists_eval(S, p):
    """격자 시각마다 목록: 기대 Σp, 실제, 흩어짐."""
    G = pd.DataFrame({"at": S["at"], "p": p, "y": S["y"]}).groupby("at")
    L = pd.DataFrame({"n": G.size(), "mu": G["p"].sum(), "real": G["y"].sum(), "sd": np.sqrt(G["p"].apply(lambda x: (x * (1 - x)).sum()))})
    L = L[L["n"] >= 10]
    L["z"] = (L["real"] - L["mu"]) / L["sd"]
    return L


def calib(p, y):
    q = pd.DataFrame({"p": p, "y": y}); q["bin"] = pd.cut(q["p"], [0, .1, .2, .3, .4, .5, .6, .7, .8, 1])
    return q.groupby("bin", observed=True).agg(n=("y", "size"), pred=("p", "mean"), real=("y", "mean"))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--check", action="store_true"); a = ap.parse_args()
    S = {ym: samples(ym) for ym in ("2601", "2603", "2606")}
    print({k: len(v) for k, v in S.items()}, flush=True)
    rows, qs = [], []
    def fold(trm, tem, feats):
        tr = pd.concat([S[x] for x in trm])
        return model().fit(tr[feats], tr["y"]).predict_proba(S[tem][feats])[:, 1]
    from sklearn.metrics import roc_auc_score
    for tem in ("2606", "2601", "2603"):
        trm = tuple(x for x in ("2601", "2603", "2606") if x != tem)
        # q: 배운 두 달 안에서 — 한 달로 배워 다른 한 달 목록의 (실제−기대)/흩어짐 10% 분위, 두 방향 중 작은 값
        q = min(float(np.quantile(lists_eval(S[c], fold((t,), c, FEATS6))["z"], 0.10)) for t, c in (trm, trm[::-1]))
        te = S[tem]; p5 = fold(trm, tem, FEATS5); p6 = fold(trm, tem, FEATS6)
        L5, L6 = lists_eval(te, p5), lists_eval(te, p6)
        lo = np.floor(L6["mu"] + q * L6["sd"])
        # 목록 안 순서: 3시간마다 목록 위 20대 — 규칙 순서(연쇄 긴 순·최근 순) vs 모델 순서
        te2 = te.reset_index(drop=True).assign(p=p6); ra = np.zeros(len(te2), bool); mo = np.zeros(len(te2), bool)
        for _, g in te2.groupby("at"):
            if len(g) < 20: continue
            i = g.index.to_numpy()
            ra[i[np.lexsort((g["age_h"].to_numpy(), -g["chain"].to_numpy()))][:20]] = True
            mo[i[np.argsort(-g["p"].to_numpy(), kind="stable")][:20]] = True
        yy = te2["y"].to_numpy().astype(float)
        olo, ohi = boot_diff(pd.to_datetime(te2["at"]).dt.normalize().to_numpy(), yy, mo, ra, n=500)
        rows.append({"배움": "+".join(trm), "시험": tem, "목록 평균": round(L6["n"].mean(), 1), "실제 평균": round(L6["real"].mean(), 1),
                     "기대(5특징)": round(L5["mu"].mean(), 1), "기대(+경과·외면)": round(L6["mu"].mean(), 1),
                     "AUC 5→7": f"{roc_auc_score(te['y'], p5):.3f}→{roc_auc_score(te['y'], p6):.3f}", "q": round(q, 2),
                     "90% 하한 평균": round(lo.mean(), 1), "하한이 맞은 %": round(100 * (L6["real"] >= lo).mean(), 1),
                     "위 20대 규칙→모델 %": f"{100 * yy[ra].mean():.1f}→{100 * yy[mo].mean():.1f} ({olo:+.1f}~{ohi:+.1f})"})
        qs.append(q)
        print(rows[-1], flush=True)
        if tem == "2606":
            cal6 = calib(p6, te["y"].to_numpy())
            age = pd.DataFrame({"age": pd.cut(te["age_h"], [0, 3, 6, 12, 24]), "y": te["y"], "p": p6}).groupby("age", observed=True).agg(n=("y", "size"), real=("y", "mean"), pred=("p", "mean"))
            print(age, flush=True)
    if a.check:
        return
    allS = pd.concat(S.values())
    m = model().fit(allS[FEATS6], allS["y"]); m._n_train = len(allS)
    X = allS[FEATS6].to_numpy(np.float64); i = np.random.default_rng(0).choice(len(X), 3000, replace=False)
    diff = np.abs(eval_trees(m, X[i]) - m.predict_proba(X[i])[:, 1]).max()
    assert diff < 1e-9, diff
    q_use = float(min(qs))
    sql = to_sql(m, FEATS6, "'목록에 올라 있는 동안' 표본")
    sql += f"\n-- 목록 90% 하한: floor(Σp + q·√Σp(1−p)), q = {q_use:.4f} (analysis/snapshot_model.py, 배울 때 안 쓴 달로 맞춤)\ncreate or replace function live.list_q() returns float8 language sql immutable as $$ select {q_use!r}::float8 $$;\n"
    (ROOT / "supabase" / "model.sql").write_text(sql)
    T = pd.DataFrame(rows)
    doc = ["# 자체 모델 — 지금 목록의 자전거마다 '다음 사람도 바로 반납할 확률' (자동 생성: `python analysis/snapshot_model.py`)", "",
           __doc__.split("\n", 1)[1].strip(), "",
           "## 왜 다시 배웠나", "",
           "처음 모델(`analysis/train_model.py`)은 헛대여가 반납된 **그 순간** 의 자전거로 배웠다. 그런데 목록의 자전거는 몇 시간째 서 있는 경우가 많고,",
           "오래 서 있을수록 다음 사람 헛대여가 낮다(그사이 누가 고쳤거나 옮겼을 수 있다). 그래서 목록에서는 확률을 크게 잡았다 — 아래 '기대(경과 없이)' vs '실제'.",
           "목록에 올라 있는 동안의 표본으로, 경과 시간과 외면(그사이 같은 대여소에서 남이 빌려 간 수)을 넣어 다시 배웠다.",
           "경과 시간만으로는 계절에 따라 뜻이 달라(한산한 1월엔 12시간 서 있는 게 보통) 잘 못 배웠고, 외면을 함께 넣자 맞았다.", "",
           "## 시험 (두 달로 배우고 남은 달로 시험, 3시간마다 목록; q 는 배운 두 달 안에서만 맞춤)", "", T.to_markdown(index=False), "",
           "## 확률이 실제와 맞나 (1·3월로 배우고 6월 목록)", "", "| 모델이 말한 확률 | 표본 | 모델 평균 | 실제 |", "|---|---:|---:|---:|"]
    doc += [f"| {b} | {int(r.n):,} | {100 * r.pred:.1f}% | {100 * r.real:.1f}% |" for b, r in cal6.iterrows()]
    doc += ["", f"최종 모델은 세 달 목록 표본 {len(allS):,}건으로 배움(그래디언트 부스팅 60그루·깊이 3, 특징 7개). SQL 식(`supabase/model.sql`)과 답 차이 {diff:.1e}.",
            f"목록 90% 하한의 q = **{q_use:.2f}** (세 조합 중 가장 조심스러운 값, `live.list_q()`).", "",
            "## 앱에서", "",
            "- 지금 목록의 자전거를 모델 확률 순으로 보여 준다(위 20대 정밀도가 세 달 모두 올랐다 — 표의 마지막 열).",
            "- '정비 먼저 볼 곳' 은 대여소마다 확률의 합(= 그 대여소에 진짜 고장일 자전거 수의 기대값) 순.",
            "- 홈 맨 위: \"이 중 약 Σp 대는 다음 사람도 바로 반납할 거예요 · 최소 ⌊Σp + q·σ⌋대(90%)\".", "",
            "DB 안 계산이 파이썬과 같은지: `python tools/supabase_live_load.py --parity-model`.",
            "적용 순서: `supabase/model.sql` → `supabase/live.sql`."]
    (ROOT / "docs" / "model.md").write_text("\n".join(doc) + "\n")
    print(f"→ supabase/model.sql, docs/model.md (표본 {len(allS):,}, q={q_use:.3f}, 차이 {diff:.1e})")


if __name__ == "__main__":
    main()
