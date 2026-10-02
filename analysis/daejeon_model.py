"""서울로 배운 AI 가 대전에서도 맞나 — 대전 타슈(2025년 5·10월)에 서울 모델을 그대로 (다시 배우지 않음)

    python analysis/daejeon_model.py      # → docs/model_daejeon.md

대전 기록엔 생년·성별이 없어 같은 사람은 '반납 2분 안 재대여' 로 본다(engine/morning.py RULE). 목록 흉내·특징·정답은 서울과 같다(analysis/snapshot_model.py).
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from engine.core import load_tashu, mark
from engine.morning import RULE
from analysis.snapshot_model import samples, samples_from, lists_eval, calib, FEATS6
from analysis.train_model import model
from analysis.ml_compare import boot_diff


def main():
    seoul = pd.concat([samples(ym) for ym in ("2601", "2603", "2606")])
    m = model().fit(seoul[FEATS6], seoul["y"])
    q = -2.3426   # supabase/model.sql 의 live.list_q
    rows = []
    for ym in ("2505", "2510"):
        M = mark(load_tashu(ROOT / "data" / "raw" / "tashu" / f"tashu_{ym}.csv"), RULE)
        S = samples_from(M).reset_index(drop=True)
        p = m.predict_proba(S[FEATS6])[:, 1]
        L = lists_eval(S, p)
        lo = np.floor(L["mu"] + q * L["sd"])
        S["p"] = p
        ra = np.zeros(len(S), bool); mo = np.zeros(len(S), bool)
        cap = 10
        for _, g in S.groupby("at"):
            if len(g) < cap: continue
            i = g.index.to_numpy()
            ra[i[np.lexsort((g["age_h"].to_numpy(), -g["chain"].to_numpy()))][:cap]] = True
            mo[i[np.argsort(-g["p"].to_numpy(), kind="stable")][:cap]] = True
        y = S["y"].to_numpy().astype(float)
        olo, ohi = boot_diff(pd.to_datetime(S["at"]).dt.normalize().to_numpy(), y, mo, ra, n=500)
        rows.append({"대전 달": f"20{ym[:2]}-{ym[2:]}", "목록 표본": len(S), "목록 평균 대수": round(L["n"].mean(), 1),
                     "기대(서울 모델)": round(L["mu"].mean(), 1), "실제": round(L["real"].mean(), 1),
                     "90% 하한이 맞은 %": round(100 * (L["real"] >= lo).mean(), 1),
                     f"위 {cap}대 규칙→모델 %": f"{100 * y[ra].mean():.1f}→{100 * y[mo].mean():.1f} ({olo:+.1f}~{ohi:+.1f})"})
        print(rows[-1], flush=True)
        if ym == "2510":
            c = calib(p, y)
    out = ["# 서울로 배운 AI 를 대전에 그대로 (자동 생성: `python analysis/daejeon_model.py`)", "", __doc__.split("\n", 1)[1].strip(), "",
           "대전 목록은 작아서(한 번에 수십 대) 위 10대로 비교한다.", "", pd.DataFrame(rows).to_markdown(index=False), "",
           "## 확률이 실제와 맞나 (대전 2025-10)", "", "| 모델이 말한 확률 | 표본 | 모델 평균 | 실제 |", "|---|---:|---:|---:|"]
    out += [f"| {b} | {int(r.n):,} | {100 * r.pred:.1f}% | {100 * r.real:.1f}% |" for b, r in c.iterrows()]
    (ROOT / "docs" / "model_daejeon.md").write_text("\n".join(out) + "\n")
    print("→ docs/model_daejeon.md")


if __name__ == "__main__":
    main()
