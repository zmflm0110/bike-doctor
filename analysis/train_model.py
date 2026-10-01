"""자체 모델 학습 → 클라우드 DB 용 SQL — 자전거마다 '다음에 빌린 다른 사람도 바로 반납할 확률'

    python analysis/train_model.py      # → supabase/model.sql (live.p_next_dud), docs/model.md

특징 5개 (그 헛대여 반납 시점, 지난 7일): 연쇄(서로 다른 사람 수), 헛대여 수, 대여 수, 이번 줄 전의 경보 수, 이번 대여 시간(초).
17개를 다 쓴 모델과 같은 정밀도라(docs/related_work.md 3-1, 아래 표) DB 안에서 셀 수 있는 5개만 쓴다. 이용자 정보는 안 쓴다.
모델: 그래디언트 부스팅 60그루·깊이 3 → 나무를 SQL CASE 식으로 바꿔 Supabase 가 5분마다 직접 계산(서버 없음).
바꾼 SQL 식이 sklearn 과 같은 답인지 이 스크립트가 직접 확인한다(파이썬으로 같은 식을 계산해 비교).
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from analysis.ml_compare import marked, features, realtime_rows, top_same_count, boot_diff, MONTHS

FEATS5 = ["chain", "hist7_duds", "hist7_rentals", "prior_alarms7", "dur_sec"]


def model():
    return HistGradientBoostingClassifier(max_iter=60, max_depth=3, learning_rate=0.1, min_samples_leaf=200,
                                          l2_regularization=1.0, early_stopping=False, random_state=0)


def trees(m):
    """sklearn 나무 → [(마디 배열)]. 잎 값에는 학습률이 이미 곱해져 있다(아래에서 확인)."""
    return [p[0].nodes for p in m._predictors]


def eval_trees(m, X):
    """SQL 로 옮길 식 그대로 파이썬에서 계산 — sklearn 과 같은지 확인용"""
    raw = np.full(len(X), m._baseline_prediction.ravel()[0], dtype=np.float64)
    for nodes in trees(m):
        for i, row in enumerate(X):
            n = 0
            while not nodes[n]["is_leaf"]:
                n = nodes[n]["left"] if row[nodes[n]["feature_idx"]] <= nodes[n]["num_threshold"] else nodes[n]["right"]
            raw[i] += nodes[n]["value"]
    return 1 / (1 + np.exp(-raw))


def sql_tree(nodes, n=0, ind="  "):
    nd = nodes[n]
    if nd["is_leaf"]:
        return repr(float(nd["value"]))
    f = FEATS5[nd["feature_idx"]]
    return (f"case when {f} <= {float(nd['num_threshold'])!r} then {sql_tree(nodes, nd['left'], ind)} "
            f"else {sql_tree(nodes, nd['right'], ind)} end")


def to_sql(m):
    body = "\n    + ".join(sql_tree(t) for t in trees(m))
    args = ", ".join(f"{f} float8" for f in FEATS5)
    return f"""-- 자동 생성: python analysis/train_model.py — 손으로 고치지 말 것
-- 자전거마다 '다음에 빌린 다른 사람도 바로 반납할 확률' (0~1). 특징은 live.p_features 와 같은 정의.
-- 그래디언트 부스팅 {len(trees(m))}그루·깊이 3, 서울 2026년 1·3·6월 헛대여 반납 {m._n_train:,}건으로 학습.
create or replace function live.p_next_dud({args}) returns float8 language sql immutable parallel safe as $$
  select 1 / (1 + exp(-(
    {float(m._baseline_prediction.ravel()[0])!r}
    + {body}
  )))
$$;
"""


def main():
    Ms = {ym: marked(ym) for ym in MONTHS}
    RT = {ym: realtime_rows(M, features(M)) for ym, M in Ms.items()}
    lines = ["# 자체 모델 — 다음 사람도 바로 반납할 확률 (자동 생성: `python analysis/train_model.py`)", "",
             __doc__.split("\n", 1)[1].strip(), "", "## 다른 달로 시험 (같은 수를 고를 때 정밀도, 괄호는 모델 − 규칙 95% 범위)", "",
             "| 배움 → 시험 | 규칙(연쇄 ≥ 2) | 모델 5특징 |", "|---|---:|---:|"]
    for trm, tem in ((("2601", "2603"), "2606"), (("2601",), "2603"), (("2603", "2606"), "2601")):
        tr = pd.concat([RT[x] for x in trm]); te = RT[tem]
        p = model().fit(tr[FEATS5], tr["y"]).predict_proba(te[FEATS5])[:, 1]
        y = te["y"].to_numpy().astype(float); rule = (te["chain"] >= 2).to_numpy(); N = int(rule.sum())
        sel = top_same_count(p, N); lo, hi = boot_diff(te["day"].to_numpy(), y, sel, rule, n=500)
        lines.append(f"| {'·'.join(str(int(x[2:])) + '월' for x in trm)} → {int(tem[2:])}월 | {100 * y[rule].mean():.1f}% | {100 * y[sel].mean():.1f}% ({lo:+.1f} \\~ {hi:+.1f}) |")
        if tem == "2606":
            q = pd.DataFrame({"p": p[rule], "y": y[rule]}); q["bin"] = pd.cut(q["p"], [0, .2, .3, .4, .5, .6, .7, .8, 1])
            cal = q.groupby("bin", observed=True).agg(n=("y", "size"), pred=("p", "mean"), real=("y", "mean"))
        print(lines[-1], flush=True)
    lines += ["", "## 확률이 실제와 맞나 (1·3월로 배우고 6월, 규칙 목록 안)", "", "| 모델이 말한 확률 | 자전거 수 | 모델 평균 | 실제 |", "|---|---:|---:|---:|"]
    lines += [f"| {b} | {int(r.n):,} | {100 * r.pred:.1f}% | {100 * r.real:.1f}% |" for b, r in cal.iterrows()]

    # 최종 모델: 세 달 전부
    allE = pd.concat(RT.values())
    m = model().fit(allE[FEATS5], allE["y"])
    m._n_train = len(allE)
    X = allE[FEATS5].to_numpy(np.float64)
    i = np.random.default_rng(0).choice(len(X), 3000, replace=False)
    diff = np.abs(eval_trees(m, X[i]) - m.predict_proba(X[i])[:, 1]).max()
    assert diff < 1e-9, f"SQL 식이 sklearn 과 다름: {diff}"
    (ROOT / "supabase" / "model.sql").write_text(to_sql(m))
    lines += ["", f"최종 모델은 세 달 {len(allE):,}건으로 학습. SQL 식(`supabase/model.sql`)과 sklearn 의 답 차이 최대 {diff:.1e} (3,000건 표본).",
              "", "## 어디에 쓰나", "",
              "목록 기준(서로 다른 2명이 연달아)은 그대로 두고, 목록에 오른 자전거마다 이 확률을 보여 준다(조회 화면 '다음 사람도 반납할 확률').",
              "규칙 목록 **안의 순서**를 바꾸는 효과는 거의 없었다(위 25% 정밀도 76\\~77% 로 같음) — 그래서 순서는 바꾸지 않는다.",
              "", "DB 안 계산이 파이썬과 같은지: `python tools/supabase_live_load.py --parity-model` (2026-10-01: 목록 86대 특징 모두 같음).",
              "적용 순서: `supabase/model.sql` → `supabase/live.sql` (live.compute 가 live.p_next_dud 를 부른다)."]
    (ROOT / "docs" / "model.md").write_text("\n".join(lines) + "\n")
    print(f"→ supabase/model.sql, docs/model.md (학습 {len(allE):,}건, SQL 식 차이 {diff:.1e})")


if __name__ == "__main__":
    main()
