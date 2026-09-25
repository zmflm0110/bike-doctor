"""Phase 2 — 공개 실시간 API(대여소별 자전거 대수)만으로 헛대여·경보를 잡을 수 있나. 과거 기록으로 시험.

대여 = 대여소 대수 −1, 반납 = +1. 과거 대여기록으로 대여소별 대수 변화를 재구성하고, Δ초마다 찍은 것처럼 묶는다.
깜빡임 = 어떤 구간 순변화가 정확히 −1, 그 대여소의 다음 변화 구간이 정확히 +1, 두 구간 사이가 3분 이내.
진짜 헛대여(같은 대여소 3분·300m) 가 만든 −1/+1 과 깜빡임이 맞아떨어지면 맞힘.
경보: 한 대여소에서 깜빡임이 W 시간 안에 2번 → "이 대여소에 고장 의심 자전거". 진짜 자전거 단위 경보(서로 다른 사람 2연속)와 비교.
※ 재배치 트럭의 대량 이동은 대여기록에 없어 빠진다(실제 API 에선 큰 점프로 보여 걸러 낼 수 있음).

    python analysis/phase2_realtime.py 2603
"""
import re, math, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from engine.core import Rule, load_seoul, mark

RULE = Rule(max_sec=180, max_m=300, alarm_k=2)
W_H = 3   # 대여소 경보: 깜빡임 2번이 이 시간 안


def run(R, dt):
    # 시각 → 초. (pandas 가 시각을 ns 가 아닌 us 로 저장할 수 있어 단위를 가정하지 않는다)
    epoch = pd.Timestamp("1970-01-01")
    t0 = ((R["t0"] - epoch).dt.total_seconds()).to_numpy().astype(np.int64)
    t1 = ((R["t1"] - epoch).dt.total_seconds()).to_numpy().astype(np.int64)
    E = pd.DataFrame({"st": np.r_[R["st0"].to_numpy(), R["st1"].to_numpy()],
                      "b": np.r_[t0 // dt, t1 // dt], "d": np.r_[-np.ones(len(R), int), np.ones(len(R), int)]})
    N = E.groupby(["st", "b"], sort=True)["d"].sum()
    N = N[N != 0].reset_index()
    same = N["st"].eq(N["st"].shift(-1))
    gap = N["b"].shift(-1) - N["b"]
    lim = math.ceil(RULE.max_sec / dt) + 1
    flip = same & (N["d"] == -1) & (N["d"].shift(-1) == 1) & (gap <= lim) & (gap >= 1)
    Fl = pd.DataFrame({"st": N.loc[flip, "st"].to_numpy(), "b0": N.loc[flip, "b"].to_numpy(),
                       "b1": N["b"].shift(-1)[flip].astype(int).to_numpy()})
    duds = R[R["dud"]]
    D = pd.DataFrame({"st": duds["st0"].to_numpy(), "b0": t0[R["dud"].to_numpy()] // dt, "b1": t1[R["dud"].to_numpy()] // dt})
    hit = D.merge(Fl, on=["st", "b0", "b1"], how="inner").drop_duplicates()
    recall = len(hit) / max(1, len(D))
    precision = len(hit) / max(1, len(Fl))

    # 대여소 경보: 깜빡임 2번이 W 시간 안
    Fl = Fl.sort_values(["st", "b1"])
    prev_same = Fl["st"].eq(Fl["st"].shift(1))
    close = prev_same & ((Fl["b1"] - Fl["b1"].shift(1)) * dt <= W_H * 3600)
    SA = Fl[close][["st", "b1"]].rename(columns={"b1": "b"})
    # 진짜 자전거 경보(서로 다른 사람 2연속)의 대여소·시각
    TA = pd.DataFrame({"st": R.loc[R["alarm"], "st1"].to_numpy(), "b": t1[R["alarm"].to_numpy()] // dt})
    # 같은 대여소에서 ±(한 구간) 안에 겹치면 맞힘
    def matched(A, B):
        B2 = pd.concat([B.assign(b=B["b"] + s) for s in (-1, 0, 1)])
        return A.merge(B2.drop_duplicates(), on=["st", "b"], how="inner").drop_duplicates().shape[0]
    alarm_recall = matched(TA, SA) / max(1, len(TA))
    alarm_precision = matched(SA, TA) / max(1, len(SA))
    return {"dt": dt, "duds": len(D), "flips": len(Fl), "dud_recall_%": round(100 * recall, 1), "flip_precision_%": round(100 * precision, 1),
            "true_alarms": len(TA), "station_alarms": len(SA),
            "alarm_recall_%": round(100 * alarm_recall, 1), "alarm_precision_%": round(100 * alarm_precision, 1)}


def by_traffic(R, dt):
    """대여소 붐비는 정도(하루 대여 수)로 나눠서."""
    days = R["t0"].dt.normalize().nunique()
    per_day = R.groupby("st0").size() / days
    tiers = [("한산(<20/일)", per_day[per_day < 20].index), ("보통(20~60)", per_day[(per_day >= 20) & (per_day < 60)].index),
             ("붐빔(≥60)", per_day[per_day >= 60].index)]
    out = []
    for name, sts in tiers:
        sub = R[R["st0"].isin(sts) & R["st1"].isin(sts)]
        # 대여소 대수는 그 대여소를 오간 모든 대여로 정해지므로, 해당 대여소가 끼는 모든 기록을 쓴다
        sub = R[R["st0"].isin(sts) | R["st1"].isin(sts)]
        r = run(sub, dt)
        out.append({"tier": name, "stations": len(sts), **{k: r[k] for k in ("dud_recall_%", "flip_precision_%", "alarm_recall_%", "alarm_precision_%")}})
    return out


if __name__ == "__main__":
    ym = sys.argv[1] if len(sys.argv) > 1 else "2603"
    R = mark(load_seoul(ROOT / "data" / "raw" / f"rent_{ym}.csv"), RULE)
    lines = [f"# Phase 2 — 공개 실시간 자료만으로 (자동 생성, 20{ym[:2]}-{ym[2:]})", "",
             "| 찍는 간격 | 헛대여 | 깜빡임 | 헛대여 잡은 비율 | 깜빡임 중 진짜 | 진짜 경보 | 대여소 경보 | 진짜 경보 잡은 비율 | 대여소 경보 중 진짜 |", "|---|---|---|---|---|---|---|---|---|"]
    for dt in (30, 60, 120):
        r = run(R, dt)
        print(r, flush=True)
        lines.append(f"| {dt}초 | {r['duds']:,} | {r['flips']:,} | {r['dud_recall_%']}% | {r['flip_precision_%']}% | {r['true_alarms']:,} | {r['station_alarms']:,} | {r['alarm_recall_%']}% | {r['alarm_precision_%']}% |")
    lines += ["", "## 60초 간격, 대여소 붐비는 정도별", "", "| 대여소 | 수 | 헛대여 잡은 비율 | 깜빡임 중 진짜 | 진짜 경보 잡은 비율 | 대여소 경보 중 진짜 |", "|---|---|---|---|---|---|"]
    for t in by_traffic(R, 60):
        print(t, flush=True)
        lines.append(f"| {t['tier']} | {t['stations']} | {t['dud_recall_%']}% | {t['flip_precision_%']}% | {t['alarm_recall_%']}% | {t['alarm_precision_%']}% |")
    md = re.sub(r"(?<!\\)~", r"\\~", "\n".join(lines))   # GitHub 은 한 줄의 ~ 두 개 사이를 취소선으로 그린다
    (ROOT / "docs" / "phase2.md").write_text(md + "\n")
