"""현장 조사 검증 — 사람이 본 자전거 상태(survey.csv)와, 그 시각까지의 대여기록으로 엔진이 낸 판단을 맞춘다.

그달 대여이력 파일이 공개되면(보통 다음 달 중순) 돌린다:
    python analysis/field_validation.py data/survey.csv data/raw/rent_2610.csv

엔진 판단 = 본 시각 직전까지 그 자전거의 '서로 다른 사람 헛대여' 연쇄 (2 이상 노랑, 3 이상 빨강)
지표:
  고장 포착률   사람이 고장이라고 본 자전거 중 엔진도 경보였던 비율
  헛경보율      사람이 멀쩡하다고 본 자전거 중 엔진이 경보였던 비율
  경보 적중률   엔진이 경보였던 자전거 중 사람이 고장이라고 본 비율
"""
import pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np, pandas as pd
from engine.core import load_seoul, mark
from engine.morning import RULE


def judge(R, bike, t):
    g = R[(R["bike"] == bike) & (R["t1"] <= t)]
    if g.empty:
        return 0
    last = g.iloc[-1]
    return int(last["streak"] + 1) if (last["dud"] and not last["retry"]) else (int(last["streak"]) if last["dud"] else 0)


def validate(survey, R):
    R = mark(R, RULE)
    S = survey.copy()
    S["at"] = pd.to_datetime(S["at"])
    S["broken"] = S["status"] != "멀쩡함"
    S["chain"] = [judge(R, b, t) for b, t in zip(S["bike"], S["at"])]
    S["alarm"] = S["chain"] >= RULE.alarm_k
    rate = lambda m: round(100 * m.mean(), 1) if len(m) else None
    return S, {"조사 대수": len(S), "고장으로 본 대수": int(S["broken"].sum()),
               "고장 포착률 %": rate(S.loc[S["broken"], "alarm"]), "헛경보율 %": rate(S.loc[~S["broken"], "alarm"]),
               "경보 적중률 %": rate(S.loc[S["alarm"], "broken"])}


if __name__ == "__main__":
    survey = pd.read_csv(sys.argv[1], encoding="utf-8-sig")
    R = load_seoul(sys.argv[2])
    S, m = validate(survey, R)
    print(m)
    S.to_csv(ROOT / "docs" / "field_validation_rows.csv", index=False, encoding="utf-8-sig")
