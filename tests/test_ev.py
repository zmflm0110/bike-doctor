"""충전기 헛충전 엔진 — 가짜 스냅샷으로 규칙을 못 박는다."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
from engine.ev import sessions, mark_ev, zombie_chargers


def snap(stat, chg, ts, te):
    return {"statId": stat, "chgerId": chg, "stat": "2", "lastTsdt": ts, "lastTedt": te}


def test_zombie_detection():
    S = pd.DataFrame([
        # 충전기 A-01: 서로 다른 시간대에 1분짜리 충전 3번 (같은 스냅샷이 여러 번 찍혀도 한 건)
        snap("A", "01", "20261001080000", "20261001080100"), snap("A", "01", "20261001080000", "20261001080100"),
        snap("A", "01", "20261001093000", "20261001093100"),
        snap("A", "01", "20261001093300", "20261001093330"),   # 3분 뒤 재시도(같은 사람) → 연쇄에 안 셈
        snap("A", "01", "20261001120000", "20261001120100"),
        # 충전기 B-01: 헛충전 한 번 뒤 정상 충전 → 연쇄 끊김
        snap("B", "01", "20261001080000", "20261001080100"), snap("B", "01", "20261001090000", "20261001100000"),
    ])
    X = sessions(S)
    assert len(X) == 6
    M = mark_ev(X)
    a = M[M["charger"] == "A-01"]
    assert a["retry"].tolist() == [False, False, True, False]
    assert a["streak"].tolist() == [0, 1, 1, 2]
    assert a["alarm"].tolist() == [False, True, False, False]
    Z = zombie_chargers(X, now="2026-10-01 13:00")
    assert Z["charger"].tolist() == ["A-01"] and Z["chain"].item() == 3
