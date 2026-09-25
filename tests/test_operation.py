"""운영 예행연습: 가짜 대여이력 API 로 매일 작업(main --source api)을 이틀 아침 연속 → 목록 파일·채점 파일·색인이 앱이 읽는 모양으로 나오는지."""
import datetime as dt, json, pathlib, sys, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import server.daily_job as job


def row(bike, t0, sec, who):
    a = dt.datetime.fromisoformat(t0)
    return {"BIKE_NO": bike, "RENT_DT": str(a), "RENT_STATION_NO": "2720", "RTN_DT": str(a + dt.timedelta(seconds=sec)),
            "RTN_STATION_NO": "2720", "USE_DST": 0 if sec < 180 else 2500, "BIRTH_YEAR": who, "GENDER": "F"}


def test_two_mornings(tmp_path, monkeypatch):
    by_day = {   # 6/9: SPB-00001 을 서로 다른 두 사람이 바로 반납 → 6/10 아침 목록. 6/10: 첫 이용자도 바로 반납 → 6/11 아침에 6/10 목록 채점
        "20260609": [row("SPB-00001", "2026-06-09 08:00:00", 30, "1990"), row("SPB-00001", "2026-06-09 09:00:00", 40, "2001"),
                     row("SPB-00002", "2026-06-09 08:00:00", 900, "1985")],
        "20260610": [row("SPB-00001", "2026-06-10 07:00:00", 20, "1970"), row("SPB-00002", "2026-06-10 08:00:00", 900, "1985")],
    }

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
            items = by_day.get(q["searchDate"], []) if q["pageNo"] == "1" else []
            b = json.dumps({"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": items}, "totalCount": len(items)}}}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out = tmp_path / "morning"
    monkeypatch.setattr(job, "OUT", out)
    monkeypatch.setattr(job, "DB", tmp_path / "daily.sqlite")
    monkeypatch.setenv("DATAGOKR_KEY", "K")
    monkeypatch.delenv("SEOUL_OPENAPI_KEY", raising=False)
    monkeypatch.setattr(job.seoul_api, "key", lambda service="seoul-openapi": "K" if service == "datagokr" else None)
    url = f"http://127.0.0.1:{srv.server_address[1]}/rent"
    try:
        job.main(["--source", "api", "--api-url", url, "--today", "2026-06-10"])
        job.main(["--source", "api", "--api-url", url, "--today", "2026-06-11"])
    finally:
        srv.shutdown()
    d10 = json.load(open(out / "2026-06-10.json"))
    assert [(b["bike"], b["chain"], b["level"], b["station_name"]) for b in d10["bikes"]] == [("SPB-00001", 2, "노랑", "힐스테이트에코")]
    d11 = json.load(open(out / "2026-06-11.json"))
    assert [b["bike"] for b in d11["bikes"]] == ["SPB-00001"] and d11["bikes"][0]["chain"] == 3   # 첫 이용자도 반납 → 연쇄 3, 빨강
    assert json.load(open(out / "index.json")) == ["2026-06-10", "2026-06-11"]
    assert json.load(open(out / "scores.json")) == {"2026-06-10": {"listed": 1, "rode": 1, "first_dud": 1}}
