"""규칙 vs 머신러닝 — '다음에 빌린 다른 사람도 바로 반납할까' 를 누가 더 잘 맞히나 (자동 생성: docs/ml_compare.md)

    python analysis/ml_compare.py            # 서울 1·3월로 배우고 6월로 시험 (처음엔 월별 파일 읽느라 1~2분)

공정하게 하려고:
  - 시험 달(6월)은 배우는 데 전혀 안 쓴다. 대여소 통계도 1·3월 것만.
  - 같은 수만큼 고른다: 규칙이 N건을 고르면 모델도 점수 높은 N건 → 그중 맞은 비율(정밀도)을 비교.
  - 날짜째로 다시 뽑기(부트스트랩)로 차이의 95% 범위를 낸다 — 같은 날·같은 자전거끼리 묶여 있어서.
  - 이용자 정보(생년·성별)는 특징으로 쓰지 않는다. 자전거·대여소·시각만.
  - 각 달 첫 7일은 뺀다(지난 7일 기록이 모자라서) — 규칙도 같은 사건만으로 잰다.

두 가지 결정을 잰다:
  실시간  헛대여가 반납될 때마다 '지금 목록에 올릴까' — 규칙: 연쇄 ≥ 2. 정답: 그 뒤 처음 빌린 다른 사람도 헛대여.
  아침    어제 마지막 대여가 헛대여인 자전거 중 '오늘 아침 목록에 올릴까' — 규칙: 연쇄 ≥ 2. 정답: 다음 날 첫 대여도 헛대여.
"""
import pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from engine.core import load_seoul, mark
from engine.morning import RULE

CACHE = ROOT / "data" / "cache" / "ml"
MONTHS = ("2601", "2603", "2606")
TRAIN, TEST = ("2601", "2603"), "2606"
FEATS = ["chain", "run_len", "run_retries", "run_span_min", "dur_sec", "dist_m", "idle_before_min", "idle_before_run_min",
         "hour", "weekend", "last_normal_ago_h", "last_normal_dur_min", "hist7_rentals", "hist7_duds", "prior_alarms7",
         "st_dud_rate", "st_log_volume"]
RNG = np.random.default_rng(0)


def marked(ym):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"M_{ym}.pkl"
    if p.exists():
        M = pd.read_pickle(p)
    else:
        M = mark(load_seoul(ROOT / "data" / "raw" / f"rent_{ym}.csv"), RULE)
        M.to_pickle(p)
    return M[M["bike"].notna()].reset_index(drop=True)   # 자전거 번호 없는 줄(6월 261건)은 뺌


def features(M):
    """대여 한 줄마다, 그 대여가 반납된 순간에 알 수 있는 것만으로 특징을 만든다."""
    M = M.reset_index(drop=True)
    n = len(M); ar = np.arange(n)
    b = M["bike"].astype(str).to_numpy()
    new_bike = np.r_[True, b[1:] != b[:-1]]
    d = M["dud"].to_numpy(); r = M["retry"].to_numpy(); s = M["streak"].to_numpy()
    t0 = M["t0"].to_numpy(); t1 = M["t1"].to_numpy()
    H = np.timedelta64(1, "h"); MIN = np.timedelta64(1, "m")
    F = pd.DataFrame(index=M.index)
    F["chain"] = np.where(d, s + 1, 0)                        # 서로 다른 사람 수 (재시도여도 그 사람은 이미 셈)
    d_prev = np.r_[False, d[:-1]] & ~new_bike
    start = d & ~d_prev                                       # 헛대여 줄의 시작
    sidx = np.maximum.accumulate(np.where(start, ar, 0))
    F["run_len"] = np.where(d, ar - sidx + 1, 0)
    cr = np.cumsum(r & d)
    F["run_retries"] = np.where(d, cr - cr[sidx] + (r & d)[sidx], 0)
    F["run_span_min"] = np.where(d, (t1 - t1[sidx]) / MIN, np.nan)
    F["dur_sec"] = (t1 - t0) / np.timedelta64(1, "s")
    F["dist_m"] = M["dist_m"].to_numpy()
    prev_t1 = np.r_[t1[:1], t1[:-1]]
    F["idle_before_min"] = np.where(new_bike, np.nan, (t0 - prev_t1) / MIN)
    ib = F["idle_before_min"].to_numpy()
    F["idle_before_run_min"] = np.where(d, ib[sidx], np.nan)
    ts = M["t1"]
    F["hour"] = ts.dt.hour.to_numpy()
    F["weekend"] = (ts.dt.dayofweek >= 5).to_numpy().astype(int)
    # 마지막 정상 이용(헛대여 아님): 언제, 얼마나 탔나
    lastn = pd.Series(np.where(~d, ar, np.nan)).groupby(b).ffill().to_numpy()
    ok = ~np.isnan(lastn); li = np.where(ok, lastn, 0).astype(int)
    F["last_normal_ago_h"] = np.where(ok, (t1 - t1[li]) / H, np.nan)
    F["last_normal_dur_min"] = np.where(ok, (t1[li] - t0[li]) / MIN, np.nan)
    # 지난 7일 이 자전거: 대여 수, 헛대여 수, 이번 줄 전의 경보 수
    alarm = (d & ~r & (s == 1)).astype(float)
    # 자전거별·시각순이므로, (자전거 번호, 시각) 을 한 줄 키로 만들어 7일 전 위치를 찾는다
    code = pd.factorize(b)[0].astype(np.int64)
    key = code * np.int64(10**12) + (t0.astype("datetime64[s]").astype(np.int64) - np.int64(1.7e9))
    j = np.searchsorted(key, key - 7 * 86400, side="left")
    csum = lambda x: np.r_[0, np.cumsum(x)]
    one, cd, ca = csum(np.ones(n)), csum(d.astype(float)), csum(alarm)
    roll = {"one": one[ar + 1] - one[j], "dud": cd[ar + 1] - cd[j], "alarm": ca[ar + 1] - ca[j]}
    F["hist7_rentals"] = roll["one"]
    F["hist7_duds"] = roll["dud"]
    F["prior_alarms7"] = roll["alarm"] - (F["chain"].to_numpy() >= 2)
    return F.astype(np.float32)


def station_stats(Ms):
    """참고 달들의 대여소별 헛대여 비율·하루 대여 수 (시험 달은 절대 안 넣음)."""
    A = pd.concat([m[["st1", "dud", "t0"]] for m in Ms])
    days = A["t0"].dt.normalize().nunique()
    g = A.groupby("st1")["dud"].agg(["mean", "size"])
    return g["mean"].to_dict(), (np.log1p(g["size"] / days)).to_dict()


def attach_station(F, M, stats):
    rate, vol = stats
    st = M["st1"].to_numpy()
    F["st_dud_rate"] = pd.Series(st).map(rate).to_numpy(dtype=float)
    F["st_log_volume"] = pd.Series(st).map(vol).to_numpy(dtype=float)
    return F


def realtime_rows(M, F):
    """헛대여 반납 사건마다: 정답 = 그 뒤 처음 빌린 다른 사람(재시도 아님)도 헛대여."""
    b = M["bike"].astype(str).to_numpy(); r = M["retry"].to_numpy(); d = M["dud"].to_numpy()
    ar = np.arange(len(M))
    nr = pd.Series(np.where(~r, ar, np.nan))
    nxt = nr.groupby(b).shift(-1).groupby(b).bfill().to_numpy()   # 다음 '재시도 아닌' 대여
    ok = d & ~np.isnan(nxt) & (M["t0"].dt.day >= 8).to_numpy()
    idx = np.where(ok)[0]
    E = F.iloc[idx].copy()
    E["y"] = d[nxt[idx].astype(int)]
    E["day"] = M["t1"].dt.normalize().to_numpy()[idx]
    return E


def morning_rows(M, F):
    """자전거·날짜마다 그날 마지막 대여가 헛대여인 것: 정답 = 다음 날 이후 첫 대여도 헛대여 (engine/morning.py 의 채점과 같음)."""
    day = M["t0"].dt.normalize()
    last = ~M.assign(day=day).duplicated(["bike", "day"], keep="last").to_numpy()
    b = M["bike"].astype(str).to_numpy(); d = M["dud"].to_numpy(); ar = np.arange(len(M))
    # 다음 날 첫 대여 = 그 자전거의 바로 다음 줄 (마지막 줄 다음은 다음 날 이후)
    has_next = np.r_[b[1:] == b[:-1], False]
    ok = last & d & has_next & (day.dt.day >= 8).to_numpy()
    idx = np.where(ok)[0]
    E = F.iloc[idx].copy()
    E["y"] = d[idx + 1]
    E["day"] = (day.to_numpy()[idx] + np.timedelta64(1, "D"))
    E["hours_to_midnight"] = (E["day"].to_numpy() - M["t1"].to_numpy()[idx]) / np.timedelta64(1, "h")
    E["last_dud"] = M["t1"].to_numpy()[idx]
    return E


def boot_diff(day, y, a, b, n=1000):
    """날짜째로 다시 뽑아 (모델 정밀도 − 규칙 정밀도) 의 95% 범위. a·b: 고른 표시(bool)."""
    days = np.unique(day)
    g = np.searchsorted(days, day)
    ya, na = np.bincount(g, y * a, len(days)), np.bincount(g, a, len(days))
    yb, nb = np.bincount(g, y * b, len(days)), np.bincount(g, b, len(days))
    out = []
    for _ in range(n):
        w = np.bincount(RNG.integers(0, len(days), len(days)), minlength=len(days))
        out.append((w @ ya) / max(1, w @ na) - (w @ yb) / max(1, w @ nb))
    return np.percentile(out, [2.5, 97.5]) * 100


def auc(y, s):
    from sklearn.metrics import roc_auc_score
    return roc_auc_score(y, s)


def fit(X, y):
    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=100,
                                       l2_regularization=1.0, early_stopping=True, validation_fraction=0.15, random_state=0)
    return m.fit(X, y)


def fit_logit(X, y):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=2000)).fit(X, y)


def top_same_count(score, k):
    """점수 높은 k 개."""
    sel = np.zeros(len(score), bool); sel[np.argsort(-score, kind="stable")[:k]] = True
    return sel


def main():
    t = time.time()
    Ms = {ym: marked(ym) for ym in MONTHS}
    print(f"읽기 {time.time() - t:.0f}s", flush=True)
    out = ["# 규칙 vs 머신러닝 (자동 생성: `python analysis/ml_compare.py`)", "",
           "**결론: 규칙을 그대로 쓴다.** 머신러닝(그래디언트 부스팅, 특징 17개)은 실시간 목록에서 같은 수를 고를 때 정밀도를 3\\~4%p 올렸고(두 달 모두), "
           "아침 목록·정비 순서에서는 달마다 들쭉날쭉했다(1\\~2%p, 또는 한 달만). 한 줄짜리 규칙이 모델 성능의 대부분을 이미 낸다는 뜻이다. "
           "모델은 설명하기 어렵고 클라우드 DB(SQL) 안에서 5분마다 돌리기도 어려워서, 3\\~4%p 를 위해 바꾸지 않는다. "
           "모델이 가장 기대는 것은 '지난 7일 이 자전거의 헛대여 수' 와 연쇄 길이 — 앱 목록에 참고로 보여 줄 만하다.", "",
           __doc__.split("\n", 1)[1].strip(), "",
           "※ 여기 실시간 정밀도(규칙 약 49%)는 목록에 올라 있는 동안의 **모든** 헛대여 반납을 한 건씩 센다(긴 연쇄가 여러 번 들어감). "
           "경보 한 건에 한 번만 세는 실시간 채점(32\\~34%, docs/per_alarm.md)과는 세는 법이 다르다 — 규칙과 모델을 **같은 사건**으로 비교하려고 이렇게 쟀다.", ""]
    RT, MO = {}, {}
    for ym, M in Ms.items():
        refs = [Ms[x] for x in TRAIN if x != ym] if ym in TRAIN else [Ms[x] for x in TRAIN]
        F = attach_station(features(M), M, station_stats(refs))
        RT[ym], MO[ym] = realtime_rows(M, F), morning_rows(M, F)
        print(ym, "실시간 사건", len(RT[ym]), "아침 후보", len(MO[ym]), f"{time.time() - t:.0f}s", flush=True)

    def run(kind, E, feats):
        tr = pd.concat([E[x] for x in TRAIN]); te = E[TEST]
        m = fit(tr[feats], tr["y"]); lg = fit_logit(tr[feats], tr["y"])
        p = m.predict_proba(te[feats])[:, 1]; pl = lg.predict_proba(te[feats])[:, 1]
        y = te["y"].to_numpy().astype(float); rule = (te["chain"] >= 2).to_numpy()
        return tr, te, m, p, pl, y, rule

    # ── 실시간
    tr, te, m, p, pl, y, rule = run("실시간", RT, FEATS)
    N = int(rule.sum())
    ml = top_same_count(p, N); lgs = top_same_count(pl, N)
    lo, hi = boot_diff(te["day"].to_numpy(), y, ml, rule)
    lo2, hi2 = boot_diff(te["day"].to_numpy(), y, lgs, rule)
    base = y.mean() * 100
    rows = [
        ("규칙 (연쇄 ≥ 2)", N, 100 * y[rule].mean(), 100 * y[rule].sum() / y.sum(), auc(y, te["chain"].to_numpy() + 1e-3 * te["run_len"].to_numpy())),
        ("로지스틱 회귀, 같은 수", N, 100 * y[lgs].mean(), 100 * y[lgs].sum() / y.sum(), auc(y, pl)),
        ("그래디언트 부스팅, 같은 수", N, 100 * y[ml].mean(), 100 * y[ml].sum() / y.sum(), auc(y, p)),
    ]
    out += ["## 1. 실시간 — 헛대여가 반납될 때마다 '목록에 올릴까'", "",
            f"시험: 2026년 6월 8\\~30일 헛대여 반납 {len(te):,}건 (배움: 1·3월 {len(tr):,}건). 그중 다음 사람도 헛대여 {base:.1f}%.", "",
            "| 방법 | 고른 수 | 정밀도 % | 잡은 비율 % (재현율) | AUC |", "|---|---:|---:|---:|---:|"]
    out += [f"| {a} | {n:,} | {pr:.1f} | {rc:.1f} | {au:.3f} |" for a, n, pr, rc, au in rows]
    out += ["", f"부스팅 − 규칙 정밀도: **{100 * (y[ml].mean() - y[rule].mean()):+.1f}%p** (95% 범위 {lo:+.1f} \\~ {hi:+.1f}), "
            f"로지스틱 − 규칙: {100 * (y[lgs].mean() - y[rule].mean()):+.1f}%p ({lo2:+.1f} \\~ {hi2:+.1f})", ""]
    # 같은 정밀도라면 몇 건 더 잡나 / 규칙 목록 안에서 순서
    inside = rule
    for frac in (0.25, 0.5):
        k = int(N * frac)
        rule_top = top_same_count(te["chain"].to_numpy().astype(float) + 1e-6 * te["run_len"].to_numpy(), k)
        ml_in = top_same_count(np.where(inside, p, -1), k)
        out.append(f"- 규칙 목록 안에서 위 {int(frac * 100)}%({k:,}건)만 본다면: 규칙 순서(연쇄 긴 순) {100 * y[rule_top].mean():.1f}% · 모델 순서 {100 * y[ml_in].mean():.1f}%")
    out.append("")
    rt_model, rt_te, rt_p = m, te, p

    # ── 아침
    tr, te, m, p, pl, y, rule = run("아침", MO, FEATS + ["hours_to_midnight"])
    day = te["day"].to_numpy()
    ml = np.zeros(len(te), bool); lgs = np.zeros(len(te), bool)
    for dd in np.unique(day):
        i = np.where(day == dd)[0]; k = int(rule[i].sum())
        ml[i[np.argsort(-p[i], kind="stable")[:k]]] = True
        lgs[i[np.argsort(-pl[i], kind="stable")[:k]]] = True
    lo, hi = boot_diff(day, y, ml, rule)
    ndays = len(np.unique(day))
    out += ["## 2. 아침 목록 — 어제 마지막이 헛대여인 자전거 중 '오늘 목록에 올릴까'", "",
            f"시험: 2026년 6월 {ndays}일, 후보 {len(te):,}대(날마다 합) · 다음 날 첫 대여도 헛대여 {100 * y.mean():.1f}%. 모델은 날마다 규칙과 같은 수를 고름.", "",
            "| 방법 | 하루 평균 | 정밀도 % | AUC |", "|---|---:|---:|---:|",
            f"| 규칙 (연쇄 ≥ 2) | {rule.sum() / ndays:.1f} | {100 * y[rule].mean():.1f} | {auc(y, te['chain'].to_numpy() + 1e-3 * te['run_len'].to_numpy()):.3f} |",
            f"| 로지스틱 회귀 | {lgs.sum() / ndays:.1f} | {100 * y[lgs].mean():.1f} | {auc(y, pl):.3f} |",
            f"| 그래디언트 부스팅 | {ml.sum() / ndays:.1f} | {100 * y[ml].mean():.1f} | {auc(y, p):.3f} |", "",
            f"부스팅 − 규칙 정밀도: **{100 * (y[ml].mean() - y[rule].mean()):+.1f}%p** (95% 범위 {lo:+.1f} \\~ {hi:+.1f})", ""]
    # 정비 인원이 하루 30대만 돌 수 있다면 — 규칙 목록 안에서 어떤 순서로?
    for cap in (20, 30):
        a = b_ = 0.0; na = nb = 0
        for dd in np.unique(day):
            i = np.where((day == dd) & rule)[0]
            if not len(i):
                continue
            ro = i[np.lexsort((-te["last_dud"].to_numpy()[i].astype("int64"), -te["chain"].to_numpy()[i]))][:cap]
            mo = i[np.argsort(-p[i], kind="stable")][:cap]
            a += y[ro].sum(); na += len(ro); b_ += y[mo].sum(); nb += len(mo)
        out.append(f"- 하루 {cap}대만 돈다면 (규칙 목록 안에서): 규칙 순서(연쇄 긴 순·최근 순) {100 * a / na:.1f}% · 모델 순서 {100 * b_ / nb:.1f}%")
    out.append("")

    # ── 다른 달로도 되나 (1월로 배우고 3월로 시험) · 두 특징만으로는 · 정비 순서
    from sklearn.tree import DecisionTreeClassifier
    two = ["chain", "hist7_duds"]
    out += ["## 3. 우연인지 — 다른 달로 다시, 그리고 간단한 모델로", "",
            "| 결정 | 배움 → 시험 | 규칙 | 부스팅(특징 전부) | 로지스틱(2개: 연쇄·지난 7일 헛대여) | 나무 깊이 3(같은 2개) |", "|---|---|---:|---:|---:|---:|"]
    for kind, E, fe in (("실시간", RT, FEATS), ("아침", MO, FEATS + ["hours_to_midnight"])):
        for trm, tem in ((TRAIN, TEST), (("2601",), "2603")):
            tr = pd.concat([E[x] for x in trm]); te = E[tem]
            y = te["y"].to_numpy().astype(float); rule = (te["chain"] >= 2).to_numpy(); N = int(rule.sum())
            pb = fit(tr[fe], tr["y"]).predict_proba(te[fe])[:, 1]
            p2 = fit_logit(tr[two], tr["y"]).predict_proba(te[two])[:, 1]
            p3 = DecisionTreeClassifier(max_depth=3, min_samples_leaf=500, random_state=0).fit(tr[two].fillna(0), tr["y"]).predict_proba(te[two].fillna(0))[:, 1] + 1e-6 * te["chain"].to_numpy()
            pr = lambda sc: 100 * y[top_same_count(sc, N)].mean()
            out.append(f"| {kind} | {'·'.join(str(int(x[2:])) + '월' for x in trm)} → {int(tem[2:])}월 | {100 * y[rule].mean():.1f} | {pr(pb):.1f} | {pr(p2):.1f} | {pr(p3):.1f} |")
    out += ["", "정비 순서 — 규칙 목록 안에서 하루 N대만 돈다면 (규칙 순서 = 연쇄 긴 순·최근 순, 괄호는 부스팅 − 규칙의 95% 범위):", ""]
    fe = FEATS + ["hours_to_midnight"]
    for trm, tem in ((TRAIN, TEST), (("2601",), "2603")):
        tr = pd.concat([MO[x] for x in trm]); te = MO[tem]
        pb = fit(tr[fe], tr["y"]).predict_proba(te[fe])[:, 1]
        y = te["y"].to_numpy().astype(float); rule = (te["chain"] >= 2).to_numpy(); day = te["day"].to_numpy()
        cells = []
        for cap in (10, 20, 30):
            a = np.zeros(len(te), bool); b_ = np.zeros(len(te), bool)
            for dd in np.unique(day):
                i = np.where((day == dd) & rule)[0]
                if len(i):
                    a[i[np.lexsort((-te["last_dud"].to_numpy()[i].astype("int64"), -te["chain"].to_numpy()[i]))][:cap]] = True
                    b_[i[np.argsort(-pb[i], kind="stable")][:cap]] = True
            lo, hi = boot_diff(day, y, b_, a)
            cells.append(f"{cap}대 {100 * y[a].mean():.1f} → {100 * y[b_].mean():.1f} ({lo:+.1f} \\~ {hi:+.1f})")
        out.append(f"- {'·'.join(str(int(x[2:])) + '월' for x in trm)} → {int(tem[2:])}월: " + " · ".join(cells))
    out.append("")

    # ── 무엇을 보고 맞히나 (실시간 모델, 시험 달 5만 건 표본)
    from sklearn.inspection import permutation_importance
    i = RNG.choice(len(rt_te), min(50000, len(rt_te)), replace=False)
    pi = permutation_importance(rt_model, rt_te[FEATS].iloc[i], rt_te["y"].iloc[i], scoring="roc_auc", n_repeats=5, random_state=0)
    imp = sorted(zip(FEATS, pi.importances_mean), key=lambda x: -x[1])
    out += ["## 4. 모델이 기대는 특징 (실시간 모델, 섞었을 때 AUC 가 떨어지는 정도)", "", "| 특징 | AUC 감소 |", "|---|---:|"]
    out += [f"| {f} | {v:.4f} |" for f, v in imp]
    out.append("")
    (ROOT / "docs" / "ml_compare.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))
    print(f"총 {time.time() - t:.0f}s")


if __name__ == "__main__":
    main()
