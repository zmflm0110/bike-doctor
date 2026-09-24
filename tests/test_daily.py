"""매일 아침 작업: 오늘 목록 기록 → 다음 날 아침 어제 목록 채점 (Phase 3 합격 기준의 '매일 기록')."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
from engine.core import _finish
from server.daily_job import db, run_morning


def ride(bike, t, sec, who):
    t0 = pd.Timestamp(t)
    return {"bike": bike, "t0": t0, "st0": "S1", "t1": t0 + pd.Timedelta(seconds=sec), "st1": "S1", "dist_m": 0 if sec < 180 else 3000, "who": who}


def test_list_then_score_next_morning(tmp_path):
    c = db(tmp_path / "d.sqlite")
    day1 = [ride("A", "2026-06-01 08:00", 30, "1990F"), ride("A", "2026-06-01 09:00", 30, "2001M"),   # 서로 다른 두 사람 헛대여
            ride("B", "2026-06-01 08:00", 900, "1985F")]
    items, scored = run_morning(c, "2026-06-02", _finish(pd.DataFrame(day1)), {})
    assert [x["bike"] for x in items] == ["A"] and scored is None
    day2 = day1 + [ride("A", "2026-06-02 07:30", 20, "1970M"), ride("A", "2026-06-02 12:00", 900, "1999F")]
    items, scored = run_morning(c, "2026-06-03", _finish(pd.DataFrame(day2)), {})
    assert scored[:4] == ("2026-06-02", 1, 1, 1)      # 목록 1대, 그날 빌림 1대, 첫 이용자 헛걸음 1
    assert items == []                                 # 정상 이용으로 연쇄 끊김 → 오늘 목록에서 빠짐
