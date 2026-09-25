"""서울 대여이력 API(tbCycleRentData)가 검증에 쓴 월별 파일과 같은 자료인가 — 같은 날을 둘 다로 받아 행·아침 목록을 맞춰 본다.
같으면 파일로 잰 모든 숫자(정밀도·선행 시간 등)가 API 로 돌리는 실시간 경보에도 그대로 선다.

    python analysis/api_parity.py 2026-06-15      (인증키 필요, 약 140번 호출)
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.core import load_seoul, from_rows, mark
from engine.morning import morning_lists
from server.seoul_api import rentals

day = sys.argv[1] if len(sys.argv) > 1 else "2026-06-15"
cache = ROOT / "data" / "cache" / f"api_{day}.json"
cache.parent.mkdir(parents=True, exist_ok=True)
if not cache.exists():
    json.dump(rentals(day), open(cache, "w"), ensure_ascii=False)
A = from_rows(json.load(open(cache)))
F = load_seoul(ROOT / "data" / "raw" / f"rent_{day[2:4]}{day[5:7]}.csv")
lo = pd.Timestamp(day)
F = F[(F["t0"] >= lo) & (F["t0"] < lo + pd.Timedelta(days=1))].reset_index(drop=True)

key = ["bike", "t0"]
M = F.merge(A, on=key, how="outer", suffixes=("_f", "_a"), indicator=True)
both = M[M["_merge"] == "both"]
out = [f"# 대여이력 API ↔ 월별 파일 ({day}) (자동 생성: `python analysis/api_parity.py {day}`)", "",
       f"| | 행 |", "|---|---|", f"| 파일 | {len(F):,} |", f"| API | {len(A):,} |",
       f"| 둘 다 (자전거·대여 시각이 같음) | {len(both):,} |", f"| 파일에만 | {(M['_merge'] == 'left_only').sum():,} |", f"| API 에만 | {(M['_merge'] == 'right_only').sum():,} |", ""]
same = {c: round(100 * (both[f"{c}_f"] == both[f"{c}_a"]).mean(), 2) for c in ("st0", "st1", "t1")}
same["who(둘 다 없음은 같음)"] = round(100 * ((both["who_f"] == both["who_a"]) | (both["who_f"].isna() & both["who_a"].isna())).mean(), 2)
same["dist_m(±1m)"] = round(100 * ((both["dist_m_f"] - both["dist_m_a"]).abs() <= 1).mean(), 2)
out += ["겹친 행에서 값이 같은 비율(%): " + ", ".join(f"{k} {v}" for k, v in same.items()), ""]
dF, dA = mark(F)["dud"].sum(), mark(A)["dud"].sum()
mF = morning_lists(F, None, with_truth=False); mA = morning_lists(A, None, with_truth=False)
nd = (lo + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
bF, bA = {x["bike"] for x in mF.get(nd, [])}, {x["bike"] for x in mA.get(nd, [])}
out += [f"헛대여: 파일 {dF:,} / API {dA:,}", "",
        f"그날 기록만으로 만든 다음 날 아침 목록: 파일 {len(bF)}대 / API {len(bA)}대, 같은 자전거 {len(bF & bA)}대"]
print("\n".join(out))
(ROOT / "docs" / "api_parity.md").write_text("\n".join(out) + "\n")
