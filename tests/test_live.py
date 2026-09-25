"""실시간 경보: 지금 연쇄가 이어진 자전거, 오래된 연쇄 빼기, 경보 채점 (네트워크 없이 가짜 기록으로)."""
import sys, pathlib, datetime as dt
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pandas as pd
from engine.core import _finish
from server import live


def ride(bike, t, sec, who, st="00101"):
    t0 = pd.Timestamp(t)
    return {"bike": bike, "t0": t0, "st0": st, "t1": t0 + pd.Timedelta(seconds=sec), "st1": st, "dist_m": 0 if sec < 180 else 3000, "who": who}


def test_live_state_and_score(tmp_path):
    now = pd.Timestamp("2026-09-25 12:00")
    R = _finish(pd.DataFrame([
        ride("A", "2026-09-25 09:00", 30, "1990F"), ride("A", "2026-09-25 10:00", 20, "2001M"),    # 서로 다른 두 사람 → 경보, 지금 목록
        ride("B", "2026-09-23 08:00", 30, "1980F"), ride("B", "2026-09-23 09:00", 30, "1999M"),    # 연쇄지만 이틀 전 → 목록에서 뺌
        ride("C", "2026-09-25 09:00", 30, "1990F"), ride("C", "2026-09-25 09:01", 30, "1990F"),    # 같은 사람 재시도 → 경보 없음
    ]))
    bikes, alarms = live.live_state(R, now, {"00101": "시험 대여소"})
    assert [b["bike"] for b in bikes] == ["A"] and bikes[0]["station_name"] == "시험 대여소" and bikes[0]["minutes_ago"] == 119
    assert sorted(alarms["bike"]) == ["A", "B"]

    c = live.db(tmp_path / "l.sqlite")
    later = pd.concat([R, _finish(pd.DataFrame([ride("A", "2026-09-25 11:00", 25, "1975M")]))])   # 경보 뒤 다른 사람도 헛대여
    later["t0"] = later["t0"].astype(str); later["t1"] = later["t1"].astype(str)
    with c:
        c.executemany("insert into rentals values (?, ?, ?, ?, ?, ?, ?)", later[live.COLS].itertuples(index=False))
        c.execute("insert into alarms values ('A', '2026-09-25 10:00:20', '00101', 2, '2026-09-25 10:01:00')")   # 1분 뒤 알아챔 → 실시간
        c.execute("insert into alarms values ('B', '2026-09-23 09:00:30', '00101', 2, '2026-09-25 11:00:00')")   # 처음 채울 때 → 실시간 아님
    s = live.score(c, now)
    assert s == {"alarms": 1, "scored": 1, "next_rider_dud": 1, "precision_%": 100.0, "waiting": 0}
    assert live.score(c, now, live_only=False)["alarms"] == 2


def test_prune_keeps_recent_only(tmp_path):
    c = live.db(tmp_path / "p.sqlite")
    with c:
        c.executemany("insert into rentals values (?, ?, '00101', ?, '00101', 0, '1990F')",
                      [("A", "2026-09-01 08:00:00", "2026-09-01 08:00:30"), ("B", "2026-09-24 08:00:00", "2026-09-24 08:00:30")])
    assert live.prune(c, dt.datetime(2026, 9, 25, 12)) == 1
    assert [b for (b,) in c.execute("select bike from rentals")] == ["B"]


def test_fetch_no_data_both_shapes(monkeypatch):
    """새 시간이 막 시작돼 자료가 없을 때 — 두 가지 응답 모양 모두 '빈 목록' 이지 오류가 아님."""
    from server import seoul_api
    for resp in ({"RESULT": {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}},
                 {"CODE": "INFO-200", "MESSAGE": "해당하는 데이터가 없습니다."}):
        monkeypatch.setattr(seoul_api, "_get", lambda url, r=resp: r)
        assert seoul_api.fetch("tbCycleRentData", "rentData", "2026-09-25/12", k="x") == []
