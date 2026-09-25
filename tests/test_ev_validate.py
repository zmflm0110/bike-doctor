"""충전기 검증: 0초 기록·기록 이상 사업자 거르기, 연쇄 뒤 다음 충전 세기 (가짜 상태 기록으로)."""
import sys, pathlib, sqlite3
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
from analysis import ev_validate as V


def snaps(rows):
    """(찍은 때, 충전소, 충전기, 시작, 종료) → 상태 표."""
    return pd.DataFrame([{"at": at, "statId": st, "chgerId": ch, "stat": "2", "statUpdDt": "", "nowTsdt": "",
                          "lastTsdt": t0, "lastTedt": t1} for at, st, ch, t0, t1 in rows])


def test_quality_and_persistence(tmp_path):
    db = tmp_path / "ev.sqlite"
    rows = [("2026-09-25T11:00:00", "AA000001", "01", "20260925100000", "20260925103000")]   # 모으기 전 충전 → 뺌
    # AA: 충전기 01 — 헛충전(1분) 셋이 서로 다른 사람(10분 넘게 떨어짐), 그 뒤 정상
    for i, (a, b) in enumerate([("110000", "110100"), ("113000", "113030"), ("120000", "120045"), ("123000", "130000")]):
        rows.append((f"2026-09-25T{a[:2]}:{a[2:4]}:59", "AA000001", "01", f"20260925{a}", f"20260925{b}"))
    # AA: 충전기 02~40 — 정상 충전 한 번씩 (사업자 평소 헛충전을 낮게)
    rows += [("2026-09-25T12:00:00", "AA000002", f"{k:02d}", "20260925110000", "20260925114000") for k in range(2, 41)]
    # BB: 0초 충전만 남기는 사업자 → 기록 이상으로 뺌
    rows += [(f"2026-09-25T11:{m:02d}:30", "BB000001", "01", f"2026092511{m:02d}00", f"2026092511{m:02d}00") for m in range(0, 50, 5)]
    S = snaps(rows)
    S.to_sql("snap", sqlite3.connect(db), index=False)
    S = V.load(db)
    X = V.sessions(S)
    assert len(X) == 4 + 39 + 10 and X["zero"].sum() == 10
    q = V.op_quality(X)
    assert bool(q.loc["AA", "clean"]) is True   # AA 는 헛충전 3/43 = 7% → 정상
    assert bool(q.loc["BB", "clean"]) is False
    base, n, out = V.persistence(X[X["op"] == "AA"])
    assert n == 43 and round(base, 3) == round(3 / 43, 3)
    assert out == [(1, 1, 1), (2, 1, 1), (3, 1, 0)]   # 1번 뒤 → 또 헛충전, 2번 뒤 → 또 헛충전, 3번 뒤 → 정상
