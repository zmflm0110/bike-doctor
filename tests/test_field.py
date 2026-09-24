"""현장 검증 스크립트가 엔진 판단을 제대로 붙이는지 — 작은 가짜 기록으로."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
from engine.core import _finish
from analysis.field_validation import validate


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
