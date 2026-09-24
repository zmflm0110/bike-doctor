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
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/rescue") as r:   # 현장 조사도 '사람 확인' 으로
            assert json.loads(r.read()) == {"SPB-69683": {"타이어": 1}, "SPB-11111": {"멀쩡함": 1}}
    finally:
        httpd.shutdown()


def test_survey_photo(tmp_path, monkeypatch):
    import base64
    monkeypatch.setattr(app, "DB", tmp_path / "p.sqlite")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    jpg = b"\xff\xd8\xff\xe0" + b"0" * 100
    ok = "data:image/jpeg;base64," + base64.b64encode(jpg).decode()

    def post(obj):
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/survey", data=json.dumps(obj).encode(), method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    try:
        assert post({"station": "1", "bike": "SPB-00001", "status": "타이어", "photo": ok}) == 200
        assert post({"station": "1", "bike": "SPB-00002", "status": "타이어", "photo": "data:image/jpeg;base64," + base64.b64encode(b"<html>").decode()}) == 400
        assert post({"station": "1", "bike": "SPB-00003", "status": "타이어", "photo": "data:text/html;base64,PGh0bWw+"}) == 400
        assert post({"station": "1", "bike": "SPB-00004", "status": "타이어", "photo": "data:image/jpeg;base64," + "A" * (app.PHOTO_MAX + 4)}) == 400
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/survey.csv") as r:
            lines = r.read().decode("utf-8-sig").strip().splitlines()
        assert len(lines) == 2 and lines[0].endswith(",photo")
        name = lines[1].split(",")[-1]
        assert (tmp_path / "photos" / name).read_bytes() == jpg
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/photo/{name}") as r:
            assert r.headers["Content-Type"] == "image/jpeg" and r.read() == jpg
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/photo/..%2Fp.sqlite")
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        httpd.shutdown()
