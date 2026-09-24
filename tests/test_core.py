"""엔진 규칙을 작은 가짜 기록으로 못 박아 둔다."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
from engine.core import Rule, mark, _finish, next_dud_table, prevented


def rentals(rows):
    """rows: (bike, 시작 '분', 걸린 초, 같은 대여소?, 거리 m, who)"""
    base = pd.Timestamp("2026-06-01 08:00")
    out = []
    for bike, m, sec, same, dist, who in rows:
        t0 = base + pd.Timedelta(minutes=m)
        out.append({"bike": bike, "t0": t0, "st0": "S1", "t1": t0 + pd.Timedelta(seconds=sec),
                    "st1": "S1" if same else "S2", "dist_m": dist, "who": who})
    return _finish(pd.DataFrame(out))


def test_dud_definition():
    R = mark(rentals([("A", 0, 60, True, 50, "1990F"),      # 헛대여
                      ("A", 10, 300, True, 50, "1991M"),    # 5분 → 아님
                      ("A", 20, 60, False, 50, "1992F"),    # 다른 대여소 → 아님
                      ("A", 30, 60, True, 900, "1993M")]))  # 900m → 아님
    assert R["dud"].tolist() == [True, False, False, False]


def test_different_people_chain_and_alarm():
    R = mark(rentals([("A", 0, 60, True, 0, "1990F"),
                      ("A", 5, 60, True, 0, "2001M"),       # 서로 다른 두 번째 헛대여 → 경보
                      ("A", 40, 900, False, 3000, "1985F")]))
    assert R["streak"].tolist() == [0, 1, 2]
    assert R["alarm"].tolist() == [False, True, False]


def test_same_person_retry_not_counted():
    R = mark(rentals([("A", 0, 60, True, 0, "1990F"),
                      ("A", 1, 60, True, 0, "1990F"),       # 같은 사람 재시도 → 연쇄에 안 셈, 경보 없음
                      ("A", 30, 900, False, 3000, "1985M")]))
    assert R["retry"].tolist() == [False, True, False]
    # 세 번째 사람 입장에서 앞서 포기한 '서로 다른 사람' 은 1명(같은 사람이 두 번 시도)
    assert R["streak"].tolist() == [0, 0, 1]
    assert not R["alarm"].any()


def test_chain_resets_on_real_ride_and_other_bike():
    R = mark(rentals([("A", 0, 60, True, 0, "1"), ("A", 5, 900, False, 3000, "2"), ("A", 30, 60, True, 0, "3"),
                      ("B", 0, 60, True, 0, "4")]))
    assert R["streak"].tolist() == [0, 1, 0, 0]


def test_tables():
    R = mark(rentals([("A", 0, 60, True, 0, "1"), ("A", 5, 60, True, 0, "2"), ("A", 9, 60, True, 0, "3")]))
    t = next_dud_table(R)
    assert t.loc[t["k"] == 2, "next_dud_%"].item() == 100.0
    assert prevented(R, Rule())["prevented"] == 1


def test_gap_proxy_when_no_who():
    """생년·성별이 없는 기록: 헛대여 반납 뒤 120초 안에 다시 빌리면 같은 사람 재시도로 본다 (docs/no_who.md)."""
    rule = Rule(retry_gap_sec=120)
    R = mark(rentals([("A", 0, 30, True, 0, None),
                      ("A", 1, 30, True, 0, None),        # 반납 30초 뒤 → 재시도
                      ("A", 10, 30, True, 0, None),       # 8분 뒤 → 다른 사람 → 연쇄 2, 경보
                      ("A", 40, 900, False, 3000, None)]), rule)
    assert R["retry"].tolist() == [False, True, False, False]
    assert R["streak"].tolist() == [0, 0, 1, 2]           # 재시도는 앞 연쇄를 그대로 이어받는다
    assert R["alarm"].tolist() == [False, False, True, False]
