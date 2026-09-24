"""구조대 서버: 정상 제보는 쌓이고, 이상한 값은 거절."""
import json, pathlib, sys, threading, urllib.request, urllib.error
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from http.server import ThreadingHTTPServer
import server.app as app


def _post(port, obj):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/rescue", data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def test_rescue_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB", tmp_path / "r.sqlite")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        assert _post(port, {"bike": "spb-12345", "verdict": "타이어", "day": "2026-06-15"}) == (200, {"ok": True, "count": 1})
        assert _post(port, {"bike": "SPB-12345", "verdict": "멀쩡함"})[1]["count"] == 2
        assert _post(port, {"bike": "XYZ", "verdict": "타이어"})[0] == 400
        assert _post(port, {"bike": "SPB-1", "verdict": "폭탄"})[0] == 400
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/rescue") as r:
            assert json.loads(r.read()) == {"SPB-12345": {"타이어": 1, "멀쩡함": 1}}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html") as r:
            assert "헛걸음 제로" in r.read().decode()
    finally:
        httpd.shutdown()


def test_survey_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "DB", tmp_path / "s.sqlite")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    def post(obj):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/survey", data=json.dumps(obj).encode(), method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None
    try:
        assert post({"station": "02720", "bike": "SPB 69683", "status": "타이어", "lat": 37.5, "lon": 127.0}) == (200, {"ok": True, "total": 1})
        assert post({"station": "02720", "bike": "SPB-11111", "status": "멀쩡함"})[1]["total"] == 2
        assert post({"bike": "SPB-1", "status": "모름"})[0] == 400
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/survey.csv") as r:
            lines = r.read().decode("utf-8-sig").strip().splitlines()
        assert lines[0].startswith("at,station,bike,status") and len(lines) == 3 and "SPB-69683" in lines[1]
    finally:
        httpd.shutdown()
