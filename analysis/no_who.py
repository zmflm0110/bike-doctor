"""자전거별 API 에 생년·성별이 없으면? — '같은 사람 재시도' 를 시간 간격으로 대신 거를 수 있나.

변형 (모두 헛대여 3분·300m, 2연속 경보):
  who     생년+성별로 같은 사람 거름 (확정 규칙)
  none    안 거름 (한 사람이 두 번 해 보면 경보)
  gap N   직전 헛대여 반납 뒤 N초 안에 다시 빌리면 같은 사람으로 봄
채점은 모두 같은 정답으로: 경보가 켜진 뒤 '진짜 다른 사람'(생년·성별 기준)이 빌렸을 때 헛걸음 비율.
간격 N 은 1월로만 고르고 3·6월에 그대로. 고르는 법(Phase 1 과 같은 생각): 정밀도가 who 규칙보다 0.5%p 넘게 낮지 않은 것 중
하루 막은 수가 가장 많은 것. ('정밀도 최대' 로 고르면 격자 끝 600초가 뽑히는데, 그건 진짜 다른 사람의 헛대여까지
재시도로 지워 경보를 줄인 대가라 막은 수가 준다 — 1월 표를 보고 이 기준으로 정했음을 적어 둔다.)
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pandas as pd
from engine.core import Rule, load_seoul, mark

RAW = ROOT / "data" / "raw"
GAPS = (30, 60, 120, 300, 600)


def score(R, truth_retry, rule):
    M = mark(R, rule)
    days = max(1, R["t0"].dt.normalize().nunique())
    after = ~truth_retry & (M["streak"].to_numpy() >= rule.alarm_k)
    d = M["dud"].to_numpy()
    return {"precision_%": round(100 * d[after].mean(), 1), "alarms_per_day": round(M["alarm"].sum() / days, 1),
            "prevented_per_day": round(d[after].sum() / days, 1)}


def run(R):
    truth = mark(R, Rule())["retry"].to_numpy()
    anon = R.assign(who=None)
    rows = [{"variant": "who (생년·성별)", **score(R, truth, Rule())},
            {"variant": "none (안 거름)", **score(anon, truth, Rule(same_person=False))}]
    for g in GAPS:
        rows.append({"variant": f"gap {g}초", **score(anon, truth, Rule(retry_gap_sec=g))})
    return pd.DataFrame(rows)


def main():
    out = ["# 생년·성별 없이 같은 사람 거르기 (자동 생성: `python analysis/no_who.py`)", ""]
    jan = run(load_seoul(RAW / "rent_2601.csv"))
    print(jan, flush=True)
    ref = jan.iloc[0]["precision_%"]
    cand = jan[jan["variant"].str.startswith("gap") & (jan["precision_%"] >= ref - 0.5)]
    best = cand.sort_values("prevented_per_day", ascending=False).iloc[0]["variant"]
    out += ["## 서울 1월 (간격을 고른 달)", "", jan.to_markdown(index=False), "", f"1월로 고른 간격: **{best}**", ""]
    summary = [f"| 달 | who 정밀도 / 하루 경보 | 안 거름 | {best} |", "|---|---|---|---|"]
    for m in ("2603", "2606"):
        T = run(load_seoul(RAW / f"rent_{m}.csv"))
        print(m, T, flush=True)
        out += [f"## 서울 20{m[:2]}-{m[2:]} (그대로 시험)", "", T.to_markdown(index=False), ""]
        w, n, g = (T.set_index("variant").loc[v] for v in ("who (생년·성별)", "none (안 거름)", best))
        summary.append(f"| 20{m[:2]}-{m[2:]} | {w['precision_%']}% / {w['alarms_per_day']} | {n['precision_%']}% / {n['alarms_per_day']} | "
                       f"{g['precision_%']}% / {g['alarms_per_day']} |")
    out += ["## 결론 (시험 달)", ""] + summary + ["",
            f"생년·성별이 없으면 **{best.split()[1]} 안 재대여를 같은 사람으로** 보면 된다 — 확정 규칙과 정밀도·경보 수가 거의 같다. "
            "안 거르면 정밀도가 떨어지고 경보가 늘어난다(한 사람이 두 번 해 보면 경보)."]
    (ROOT / "docs" / "no_who.md").write_text("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
