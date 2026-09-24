"""Phase 3 예행연습 — 키 2 가 오기 전에, 운영과 똑같은 매일 아침 작업(run_morning)을 월별 파일로 N일 연속 돌려 본다.

매일 아침 D: 최근 LOOKBACK 일(D-LOOKBACK ~ D-1) 기록만 넘긴다(API 로 받을 양과 같게) → 오늘 목록 기록 + 어제 목록 채점.
확인하는 것: (1) 7일 연속 목록이 만들어지고 매일 채점이 쌓이나 (2) 일주일 창으로 자른 목록이 한 달 전체로 만든 목록과 같나.

    python server/rehearse.py --month 2606 --start 2026-06-08 --days 7
"""
import argparse, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.core import load_seoul
from engine.morning import morning_lists
from server.daily_job import LOOKBACK_DAYS, db, run_morning


def rehearse(R, start, n_days, lookback, dbpath, stn):
    dbpath.unlink(missing_ok=True)
    c = db(dbpath)
    full = morning_lists(R, None, with_truth=False)
    rows = []
    for D in pd.date_range(start, periods=n_days + 1):          # 마지막 날은 앞날 채점만
        day = D.strftime("%Y-%m-%d")
        W = R[(R["t0"] >= D - pd.Timedelta(days=lookback)) & (R["t0"] < D)]
        items, scored = run_morning(c, day, W, stn)
        a, b = {x["bike"] for x in items}, {x["bike"] for x in full.get(day, [])}
        rows.append({"day": day, "listed": len(items), "same_as_full_%": round(100 * len(a & b) / max(1, len(a | b)), 1),
                     "missed_vs_full": len(b - a), "scored_day": scored[0] if scored else None,
                     "rode": scored[2] if scored else None, "first_dud": scored[3] if scored else None})
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default="2606")
    ap.add_argument("--start", default="2026-06-08")
    ap.add_argument("--days", type=int, default=7)
    a = ap.parse_args()
    stn = {s["id"]: s["name"] for s in json.load(open(ROOT / "web" / "data" / "stations.json"))}
    R = load_seoul(ROOT / "data" / "raw" / f"rent_{a.month}.csv")
    out = ["# Phase 3 예행연습 (자동 생성: `python server/rehearse.py`)", "",
           f"서울 {a.month} 파일로 운영과 같은 매일 아침 작업을 {a.days}일 연속. 매일 최근 N일 기록만 넘김.", ""]
    for lb in (1, 3, LOOKBACK_DAYS):
        T = rehearse(R, a.start, a.days, lb, ROOT / "data" / f"rehearsal_{lb}d.sqlite", stn)
        s = T.dropna(subset=["rode"])
        rate = 100 * s["first_dud"].sum() / max(1, s["rode"].sum())
        print(f"창 {lb}일: 전체 목록과 같음 평균 {T['same_as_full_%'].mean():.1f}%, 첫 이용자 헛걸음 {rate:.1f}%", flush=True)
        out += [f"## 최근 {lb}일 창" + (" (운영 설정)" if lb == LOOKBACK_DAYS else ""), "", T.to_markdown(index=False), "",
                f"한 달 전체로 만든 목록과 같은 비율 평균 **{T['same_as_full_%'].mean():.1f}%**, "
                f"채점 {len(s)}일 동안 목록 자전거를 그날 처음 빌린 사람 {int(s['rode'].sum())}명 중 헛걸음 **{rate:.1f}%**", ""]
    (ROOT / "docs" / "phase3_rehearsal.md").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
