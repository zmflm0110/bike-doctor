"""명령 하나로 핵심 결과를 다시 만든다 → docs/results.md

    python analysis/report.py
"""
import pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.core import Rule, load_seoul, load_tashu, load_faults, mark, next_dud_table, prevented, lead_time, unreported_chains

RAW = ROOT / "data" / "raw"
SETS = [("서울", "2026-01", load_seoul, RAW / "rent_2601.csv"),
        ("서울", "2026-03", load_seoul, RAW / "rent_2603.csv"),
        ("서울", "2026-06", load_seoul, RAW / "rent_2606.csv"),
        ("대전", "2025-05", load_tashu, RAW / "tashu" / "tashu_2505.csv"),
        ("대전", "2025-10", load_tashu, RAW / "tashu" / "tashu_2510.csv")]


def main():
    rule = Rule(max_sec=180, max_m=300, alarm_k=2)   # Phase 1 에서 1월로 확정한 규칙
    F = load_faults(RAW / "fault_2601-2606.csv")
    lines = ["# 핵심 결과 (자동 생성: `python analysis/report.py`)", "",
             f"규칙: 헛대여 = 같은 대여소 {rule.max_sec}초 안 · {rule.max_m:.0f}m 미만 반납, 경보 = 서로 다른 사람 헛대여 {rule.alarm_k}연속.",
             "대전은 생년·성별이 없어 같은 사람 재시도를 거를 수 없다(서울은 거르면 오히려 연쇄2 값이 높아진다).",
             "'막을 수 있던 헛걸음' = 경보가 켜진 뒤 그 자전거를 빌려 또 헛걸음한 사람 수. 신고 관련 열은 서울만(대전 고장신고 자료 없음).", "",
             "| 도시 | 달 | 대여 | 헛대여 % | 연쇄0 → 다음 헛대여 | 연쇄1 | **연쇄2** | 연쇄3 | 막을 수 있던 헛걸음/일 | 경보가 먼저 있던 신고 % | 경보→신고(중앙값, 시간) | 그 사이 헛걸음(평균) | 연쇄 중 7일 무신고 % |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for city, month, loader, path in SETS:
        t = time.time()
        R = mark(loader(path), rule)
        T = next_dud_table(R).set_index("k")["next_dud_%"]
        P = prevented(R, rule)
        L = lead_time(R, F) if city == "서울" else {}
        U = unreported_chains(R, F) if city == "서울" else "—"
        cell = lambda k: f"{T.get(k, float('nan')):.1f}%"
        lines.append(f"| {city} | {month} | {len(R):,} | {100*R['dud'].mean():.2f} | {cell(0)} | {cell(1)} | **{cell(2)}** | {cell(3)} | "
                     f"{P['per_day']} | {L.get('share_%', '—')} | {L.get('lead_h_median', '—')} | {L.get('victims_mean', '—')} | {U} |")
        print(f"{city} {month}: {time.time()-t:.0f}초", flush=True)
    (ROOT / "docs" / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
