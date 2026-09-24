"""대여이력 API 연결 (명세 확인 전 대비): 응답 형식 두 가지·쪽 넘기기·열 이름 맞추기, 키는 환경변수로도."""
import datetime as dt, json, pathlib, sys, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import pytest
from engine.core import from_rows
from server import seoul_api
from server.daily_job import fetch_rentals_api, run_morning, db


def row(bike, t0, sec, st="2720", who=("1990", "F"), eng=False):
    a = dt.datetime.fromisoformat(t0)
    b = a + dt.timedelta(seconds=sec)
    if eng:
        return {"BIKE_NO": bike, "RENT_DT": str(a), "RENT_STATION_NO": st, "RTN_DT": str(b), "RTN_STATION_NO": st,
                "USE_DST": 0 if sec < 180 else 2500, "BIRTH_YEAR": who[0], "GENDER": who[1]}
    return {"자전거번호": bike, "대여일시": str(a), "대여 대여소번호": st, "반납일시": str(b), "반납대여소번호": st,
            "이용거리(M)": 0 if sec < 180 else 2500, "생년": who[0], "성별": who[1]}


def test_from_rows_names_and_station_padding():
    R = from_rows([row("SPB-1", "2026-06-01 08:00:00", 30, eng=True), row("SPB-1", "2026-06-01 09:00:00", 40, who=("2001", "M"), eng=True)])
    assert list(R.columns) == ["bike", "t0", "st0", "t1", "st1", "dist_m", "who"]
    assert R["st0"].tolist() == ["02720", "02720"] and R["who"].tolist() == ["1990F", "2001M"]
    with pytest.raises(KeyError, match="받은 열"):
        from_rows([{"foo": 1, "BIKE_NO": "x"}])


def test_key_from_env(monkeypatch):
    monkeypatch.setenv("DATAGOKR_KEY", "abc")
    assert seoul_api.key("datagokr") == "abc"


@pytest.mark.parametrize("style", ["standard", "odcloud"])
def test_fetch_pages_days_then_morning_list(style, tmp_path):
    by_day = {"20260601": [row("SPB-00001", "2026-06-01 08:00:00", 30), row("SPB-00001", "2026-06-01 12:00:00", 25, who=("2001", "M"))]
                          + [row(f"SPB-{i:05d}", "2026-06-01 10:00:00", 900) for i in range(2, 7)],
              "20260602": [row("SPB-00002", "2026-06-02 07:00:00", 900)]}
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            seen.append(q)
            assert q["serviceKey"] == "K"
            items = by_day.get(q["searchDate"], [])
            n, p = int(q["numOfRows"]), int(q["pageNo"])
            part = items[(p - 1) * n: p * n]
            if style == "standard":
                body = {"response": {"header": {"resultCode": "00", "resultMsg": "OK"},
                                     "body": {"items": {"item": part[0] if len(part) == 1 else part} if part else "", "totalCount": len(items)}}}
            else:
                body = {"data": part, "totalCount": len(items), "page": p}
            b = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        R = fetch_rentals_api(dt.date(2026, 6, 1), dt.date(2026, 6, 2), url=f"http://127.0.0.1:{srv.server_address[1]}/rent", key="K", per_page=3)
    finally:
        srv.shutdown()
    assert len(R) == 8 and len(seen) == 3 + 1          # 6/1 은 7건을 3건씩 3쪽, 6/2 는 1쪽
    items, _ = run_morning(db(tmp_path / "d.sqlite"), "2026-06-02", R[R["t0"] < "2026-06-02"], {"02720": "힐스테이트에코"})
    assert [(x["bike"], x["chain"], x["station_name"]) for x in items] == [("SPB-00001", 2, "힐스테이트에코")]


def test_api_error_is_loud(tmp_path):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            b = json.dumps({"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY IS NOT REGISTERED ERROR."}}}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        with pytest.raises(RuntimeError, match="NOT REGISTERED"):
            fetch_rentals_api(dt.date(2026, 6, 1), dt.date(2026, 6, 1), url=f"http://127.0.0.1:{srv.server_address[1]}/", key="K")
    finally:
        srv.shutdown()
