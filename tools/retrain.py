"""스스로 배우기 — 클라우드 DB 가 쌓은 실시간 정답(live.samples)으로 AI 모델을 점검하고, 나을 때만 바꾼다.

    python tools/retrain.py            # 점검만: 지금 모델이 실시간 목록에서 얼마나 맞나 → docs/model_live.md
    python tools/retrain.py --deploy   # 새 모델(지난 기록 + 실시간)이 최근 자료에서 더 나으면 supabase/model.sql 을 바꾸고 DB 에 적용

규칙(과적합·우연 방지):
  - 실시간 표본을 시간순으로 앞 70% / 뒤 30% 로 나눠, 새 모델은 '지난 석 달 + 앞 70%' 로 배우고 '뒤 30%' 로만 비교한다.
  - 비교 지표는 로그 손실(확률이 얼마나 맞나). 새 모델이 지금 모델보다 2% 넘게 좋고, 기대 수가 실제와 더 가까울 때만 바꾼다.
  - 정답이 있는 실시간 표본이 500개 미만이면 점검만 하고 바꾸지 않는다.
DB 비밀번호는 키체인 'supabase-db'.
"""
import argparse, datetime as dt, io, pathlib, subprocess, sys, os
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from tools.supabase_live_load import psql, DSN
from server.seoul_api import key
from analysis.snapshot_model import samples, FEATS6
from analysis.train_model import model, to_sql, eval_trees

MIN_LIVE = 500


def live_samples():
    out = psql("copy (select to_char(at, 'YYYY-MM-DD HH24:MI:SS'), bike, " + ", ".join(FEATS6) + ", p, next_dud from live.samples "
               "where next_dud is not null order by at) to stdout with csv")
    S = pd.read_csv(io.StringIO(out), names=["at", "bike"] + FEATS6 + ["p", "y"], parse_dates=["at"])
    S["y"] = S["y"].map({"t": 1, "f": 0, True: 1, False: 0}).astype(float)
    return S


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def report(S, lines):
    days = S["at"].dt.normalize().nunique()
    L = S.groupby("at").agg(n=("y", "size"), mu=("p", "sum"), real=("y", "sum"))
    lines += [f"실시간 표본(정답 있음) {len(S):,}개 · {days}일 · 목록 {len(L)}번", "",
              f"| | 모델 확률 평균 | 실제 | 로그 손실 |", "|---|---:|---:|---:|",
              f"| 지금 모델(그때 확률) | {100 * S['p'].mean():.1f}% | {100 * S['y'].mean():.1f}% | {logloss(S['y'].to_numpy(), S['p'].to_numpy()):.4f} |", "",
              f"목록 한 번에 기대 {L['mu'].mean():.1f}대 vs 실제 {L['real'].mean():.1f}대 (평균)."]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--deploy", action="store_true"); a = ap.parse_args()
    S = live_samples()
    lines = [f"# 실시간 점검 — AI 모델이 지금 목록에서 맞나 (자동 생성: `python tools/retrain.py`, {dt.date.today()})", "", __doc__.split("\n", 1)[1].strip(), ""]
    if len(S) == 0:
        lines.append("아직 정답이 정해진 실시간 표본이 없다(3시간마다 쌓이고, 다음 사람이 빌린 뒤 7시간 지나야 정답이 정해진다).")
        (ROOT / "docs" / "model_live.md").write_text("\n".join(lines) + "\n"); print(lines[-1]); return 0
    report(S, lines)
    decision = "바꾸지 않음"
    if len(S) >= MIN_LIVE:
        cut = S["at"].quantile(0.7)
        old, new = S[S["at"] <= cut], S[S["at"] > cut]
        hist = pd.concat([samples(ym) for ym in ("2601", "2603", "2606")])
        tr = pd.concat([hist[FEATS6 + ["y"]], old[FEATS6 + ["y"]]])
        m = model().fit(tr[FEATS6], tr["y"])
        p_new = m.predict_proba(new[FEATS6])[:, 1]
        y = new["y"].to_numpy()
        ll_cur, ll_new = logloss(y, new["p"].to_numpy()), logloss(y, p_new)
        gap_cur = abs(new["p"].sum() - y.sum()); gap_new = abs(p_new.sum() - y.sum())
        better = ll_new < ll_cur * 0.98 and gap_new <= gap_cur
        lines += ["", f"## 다시 배우기 비교 (뒤 30% = {len(new):,}개, {new['at'].min():%m-%d} 부터)", "",
                  "| | 로그 손실 | 기대 합 | 실제 합 |", "|---|---:|---:|---:|",
                  f"| 지금 모델 | {ll_cur:.4f} | {new['p'].sum():.1f} | {y.sum():.0f} |",
                  f"| 새 모델(지난 기록 + 실시간 앞 70%) | {ll_new:.4f} | {p_new.sum():.1f} | {y.sum():.0f} |"]
        if better:
            decision = "새 모델이 더 나음"
            if a.deploy:   # 실시간 전부 더해 다시 배워 배포
                full = pd.concat([hist[FEATS6 + ["y"]], S[FEATS6 + ["y"]]])
                m = model().fit(full[FEATS6], full["y"]); m._n_train = len(full)
                X = full[FEATS6].to_numpy(np.float64); i = np.random.default_rng(0).choice(len(X), 3000, replace=False)
                assert np.abs(eval_trees(m, X[i]) - m.predict_proba(X[i])[:, 1]).max() < 1e-9
                old_sql = (ROOT / "supabase" / "model.sql").read_text()
                q_line = old_sql[old_sql.index("\n-- 목록 90% 하한"):]
                (ROOT / "supabase" / "model.sql").write_text(to_sql(m, FEATS6, f"목록 표본 + 실시간 {len(S):,}개({dt.date.today()} 다시 배움)") + q_line)
                env = {**os.environ, "PGPASSWORD": key("supabase-db")}
                subprocess.run(["psql", DSN, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-f", str(ROOT / "supabase" / "model.sql")], env=env, check=True)
                decision = "새 모델로 바꿈 (supabase/model.sql, DB 적용)"
    else:
        lines += ["", f"실시간 표본이 {MIN_LIVE}개 이상 모이면 다시 배우기를 비교한다(지금 {len(S)}개)."]
    lines += ["", f"**결정: {decision}**"]
    (ROOT / "docs" / "model_live.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[-12:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
