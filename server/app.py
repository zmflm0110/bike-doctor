"""작은 서버 — 웹앱(web/)을 내보내고, 구조대 확인을 받아 SQLite 에 쌓는다. 표준 라이브러리만.

    python server/app.py            # http://localhost:8765
API
  POST /api/rescue   {"bike": "SPB-12345", "verdict": "체인·기어", "day": "2026-06-15"}  → {"ok": true, "count": n}
  GET  /api/rescue   → 자전거별 확인 수·결과 요약 (정비 순위에 '사람이 확인함' 표시용)
"""
import json, pathlib, sqlite3, sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "rescue.sqlite"
VERDICTS = {"체인·기어", "타이어", "안장·핸들", "브레이크", "멀쩡함"}


def db():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("create table if not exists rescue(id integer primary key, bike text, verdict text, day text, at text default current_timestamp)")
    return c


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "web"), **kw)

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/rescue":
            return self._json(404, {"ok": False})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 2000:
                return self._json(413, {"ok": False})
            x = json.loads(self.rfile.read(n))
            bike, verdict, day = str(x["bike"])[:16].upper(), str(x["verdict"]), str(x.get("day", ""))[:10]
            if not bike.startswith("SPB-") or verdict not in VERDICTS:
                return self._json(400, {"ok": False, "error": "bike 는 SPB-, verdict 는 정해진 값"})
        except (ValueError, KeyError, json.JSONDecodeError):
            return self._json(400, {"ok": False})
        with db() as c:
            c.execute("insert into rescue(bike, verdict, day) values (?,?,?)", (bike, verdict, day))
            cnt = c.execute("select count(*) from rescue where bike=?", (bike,)).fetchone()[0]
        self._json(200, {"ok": True, "count": cnt})

    def do_GET(self):
        if self.path.startswith("/api/rescue"):
            with db() as c:
                rows = c.execute("select bike, verdict, count(*) from rescue group by bike, verdict").fetchall()
            out = {}
            for bike, verdict, n in rows:
                out.setdefault(bike, {})[verdict] = n
            return self._json(200, out)
        return super().do_GET()

    def log_message(self, *a):
        pass


def serve(port=8765):
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"http://localhost:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8765)
