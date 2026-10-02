"""현장 검증 스크립트가 엔진 판단을 제대로 붙이는지 — 작은 가짜 기록으로."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
from engine.core import _finish
from analysis.field_validation import validate, wilson, to_markdown


def test_validate():
    base = pd.Timestamp("2026-10-01 08:00")
    rows = []
    for i, who in enumerate(["1", "2", "3"]):          # A: 서로 다른 세 사람 헛대여 → 연쇄 3
        t0 = base + pd.Timedelta(minutes=10 * i)
        rows.append({"bike": "SPB-00001", "t0": t0, "st0": "S", "t1": t0 + pd.Timedelta(seconds=60), "st1": "S", "dist_m": 0, "who": who})
    t0 = base                                            # B: 정상 이용
    rows.append({"bike": "SPB-00002", "t0": t0, "st0": "S", "t1": t0 + pd.Timedelta(minutes=20), "st1": "T", "dist_m": 3000, "who": "9"})
    R = _finish(pd.DataFrame(rows))
    survey = pd.DataFrame([{"at": "2026-10-01 09:00:00", "bike": "SPB-00001", "status": "체인·기어"},
                           {"at": "2026-10-01 09:00:00", "bike": "SPB-00002", "status": "멀쩡함"}])
    S, m = validate(survey, R)
    assert S["chain"].tolist() == [3, 0]
    assert m["고장 포착률 %"] == 100.0 and m["헛경보율 %"] == 0.0 and m["경보 적중률 %"] == 100.0
    assert m["경보 적중률 95%"] == wilson(1, 1)
    md = to_markdown(S.assign(station="S"), m)
    assert "| 경보 적중률 | 100.0% (" in md and "| 체인·기어 | 1 | 1 |" in md
    # AI 확률 줄: 경보 자전거 4대 이상이면 중앙값으로 둘로 나눠 고장 비율
    S4 = pd.DataFrame({"at": ["2026-10-01 09:00:00"] * 4, "bike": [f"SPB-1000{i}" for i in range(4)], "status": ["타이어", "타이어", "멀쩡함", "멀쩡함"],
                       "broken": [True, True, False, False], "alarm": [True] * 4, "chain": [3] * 4, "p_ai": [0.8, 0.7, 0.3, 0.2], "station": ["S"] * 4})
    md4 = to_markdown(S4, {**m, "조사 대수": 4})
    assert "| AI 확률 50% 이상 | 2 | 75% | 100% (" in md4 and "| 50% 미만 | 2 | 25% | 0% (" in md4


def test_wilson():
    assert wilson(0, 0) is None
    lo, hi = wilson(10, 20)
    assert lo < 50 < hi and (lo, hi) == (29.9, 70.1)
    assert wilson(0, 10)[0] == 0.0 and wilson(0, 10)[1] > 20   # 0/10 이어도 '0%' 로 단정 못 함
