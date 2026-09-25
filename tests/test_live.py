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
    assert s == {"alarms": 1, "scored": 1, "next_rider_dud": 1, "precision_%": 100.0, "waiting": 0, "held_thin_feed": 0}
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


def _hours(c, counts):
    with c:
        c.executemany("insert into hours values (?, ?, '2026-09-25T12:00:00')", counts.items())


def test_feed_health_thin_vs_quiet_day(tmp_path):
    """자료가 끊긴 시간(가장 한산한 날의 30% 미만)만 모자람 — 명절처럼 진짜 한산한 날은 아님."""
    c = live.db(tmp_path / "h.sqlite")
    counts = {f"2026-09-{d:02d}/14": n for d, n in [(18, 6000), (19, 8000), (20, 8500), (21, 5700), (22, 5800), (23, 8300), (24, 6800)]}
    counts |= {f"2026-09-{d:02d}/07": n for d, n in [(18, 11000), (19, 3500), (20, 2600), (21, 11600), (22, 12100), (23, 10900)]}
    counts |= {"2026-09-24/07": 2400, "2026-09-25/14": 380, "2026-09-25/13": 3000}
    _hours(c, counts)
    now = dt.datetime(2026, 9, 25, 15, 30)
    h = live.hour_health(c, now)
    assert live.thin_hours(h) == {"2026-09-25/14"}          # 추석 아침(평일 중앙값의 22%)은 모자람 아님
    assert live.feed_status(h, now) == {"ok": False, "since": "2026-09-25T14:00", "ratio": round(380 / 6800, 3)}
    assert live.feed_status(h, dt.datetime(2026, 9, 25, 14, 30)) == {"ok": True}   # 지금 시간은 아직 덜 찼으니 판단 안 함


def test_score_held_when_next_rider_may_be_missing(tmp_path):
    """경보와 다음 대여 사이에 자료가 빠진 시간이 끼면 채점 보류 — 빠진 대여가 진짜 다음 사람일 수 있다."""
    c = live.db(tmp_path / "s.sqlite")
    R = _finish(pd.DataFrame([ride("A", "2026-09-25 13:00", 30, "1990F"), ride("A", "2026-09-25 13:20", 20, "2001M"),
                              ride("A", "2026-09-25 15:10", 25, "1975M")]))
    R["t0"] = R["t0"].astype(str); R["t1"] = R["t1"].astype(str)
    with c:
        c.executemany("insert into rentals values (?, ?, ?, ?, ?, ?, ?)", R[live.COLS].itertuples(index=False))
        c.execute("insert into alarms values ('A', '2026-09-25 13:20:20', '00101', 2, '2026-09-25 13:21:00')")
    _hours(c, {f"2026-09-{d:02d}/14": 6000 for d in range(18, 25)} | {"2026-09-25/14": 300})
    s = live.score(c, pd.Timestamp("2026-09-25 17:00"))
    assert s["held_thin_feed"] == 1 and s["scored"] == 0


def test_fetch_pages_until_short_page(monkeypatch):
    """실시간 대여소(bikeList)는 list_total_count 가 그 쪽 건수 — 전체 수를 믿으면 첫 1,000곳에서 멈춘다."""
    from server import seoul_api
    n = 2747
    def fake(url):
        a, b = map(int, url.rstrip("/").split("/")[-2:])
        rows = [{"i": i} for i in range(a, min(b, n) + 1)]
        return {"rentBikeStatus": {"list_total_count": len(rows), "row": rows}} if rows else {"CODE": "INFO-200"}
    monkeypatch.setattr(seoul_api, "_get", fake)
    assert len(seoul_api.fetch("bikeList", "rentBikeStatus", k="x")) == 2747
    n = 3000   # 딱 떨어질 때: 다음 쪽의 '자료 없음' 으로 끝
    assert len(seoul_api.fetch("bikeList", "rentBikeStatus", k="x")) == 3000
