"""작은 서버 — 웹앱(web/)을 내보내고, 구조대 확인을 받아 SQLite 에 쌓는다. 표준 라이브러리만.

    python server/app.py            # http://localhost:8765
    python server/app.py 8443 --https   # 집 와이파이 안 https (아이폰 위치·QR) — 먼저 server/https_local.sh
API
  POST /api/rescue   {"bike": "SPB-12345", "verdict": "체인·기어", "day": "2026-06-15"}  → {"ok": true, "count": n}
  GET  /api/rescue   → 자전거별 확인 수·결과 요약 (정비 순위에 '사람이 확인함' 표시용)
  POST /api/survey   현장 조사: {"station": "02720", "bike": "SPB-12345", "status": "타이어", "note": "", "lat": .., "lon": ..,
                     "photo": "data:image/jpeg;base64,..."(선택, 폰에서 줄인 사진 — data/photos/ 에 저장)}
  GET  /api/survey.csv  현장 조사 전체를 CSV 로 (analysis/field_validation.py 가 읽음, photo 열 = 사진 파일 이름)
  GET  /api/photo/<이름>  저장한 사진
"""
import base64, json, os, pathlib, re, sqlite3, sys, uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = pathlib.Path(os.environ.get("BIKE_DB") or ROOT / "data" / "rescue.sqlite")   # 검사는 BIKE_DB 로 따로
PHOTO_MAX = 1_500_000   # 줄인 사진 한 장(base64) 상한 — 폰에서 긴 변 1280px JPEG 로 줄여 보낸다
VERDICTS = {"체인·기어", "타이어", "안장·핸들", "브레이크", "멀쩡함"}
STATUSES = VERDICTS | {"기타 고장"}


def norm_bike(x):
    """'spb 69683', 'SPB69683', 'SPB-69683' → 'SPB-69683'. 번호가 없으면 None."""
    m = re.search(r"SPB\s*-?\s*(\d{3,6})", str(x).upper())
    return f"SPB-{int(m.group(1)):05d}" if m else None


def db():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("create table if not exists rescue(id integer primary key, bike text, verdict text, day text, at text default current_timestamp)")
    c.execute("create table if not exists survey(id integer primary key, at text default (datetime('now','localtime')), station text, bike text,"
              " status text, note text, lat real, lon real)")
    if "photo" not in [r[1] for r in c.execute("pragma table_info(survey)")]:   # 예전 DB 에 사진 열 더하기
        c.execute("alter table survey add column photo text")
    return c


def photos():
    return DB.parent / "photos"   # DB 옆 (검사는 임시 DB 옆)


def save_photo(data_url):
    """'data:image/jpeg;base64,...' → data/photos/<무작위>.jpg, 파일 이름. JPEG·PNG 만, 크기 제한."""
    m = re.fullmatch(r"data:image/(jpeg|png);base64,([A-Za-z0-9+/=]+)", data_url or "")
    if not m or len(m.group(2)) > PHOTO_MAX:
        raise ValueError("photo")
    raw = base64.b64decode(m.group(2), validate=True)
    if not (raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n"):   # 내용도 진짜 그림인지
        raise ValueError("photo")
    photos().mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex[:16]}.{'jpg' if m.group(1) == 'jpeg' else 'png'}"
    (photos() / name).write_bytes(raw)
    return name


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

    def _body(self, limit=4000):
        n = int(self.headers.get("Content-Length", 0))
        if n > limit:
            raise ValueError("too big")
        return json.loads(self.rfile.read(n))

    def do_POST(self):
        if self.path == "/api/survey":
            return self._survey()
        if self.path != "/api/rescue":
            return self._json(404, {"ok": False})
        try:
            x = self._body()
            bike, verdict, day = norm_bike(x["bike"]), str(x["verdict"]), str(x.get("day", ""))[:10]
            if not bike or verdict not in VERDICTS:
                return self._json(400, {"ok": False, "error": "bike 는 SPB-, verdict 는 정해진 값"})
        except (ValueError, KeyError, json.JSONDecodeError):
            return self._json(400, {"ok": False})
        with db() as c:
            c.execute("insert into rescue(bike, verdict, day) values (?,?,?)", (bike, verdict, day))
            cnt = c.execute("select count(*) from rescue where bike=?", (bike,)).fetchone()[0]
        self._json(200, {"ok": True, "count": cnt})

    def _survey(self):
        try:
            x = self._body(limit=PHOTO_MAX + 4000)
            bike, status = norm_bike(x["bike"]), str(x["status"])
            if not bike or status not in STATUSES:
                return self._json(400, {"ok": False, "error": "bike 는 SPB-, status 는 정해진 값"})
            import datetime as _dt
            # 폰에 모아 뒀다 늦게 보낸 기록도 '본 시각' 으로 남긴다 (없으면 서버 시각)
            at = _dt.datetime.fromisoformat(str(x["at"]).replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M:%S") \
                if x.get("at") else _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            row = (at, str(x.get("station", ""))[:10], bike, status, str(x.get("note", ""))[:200],
                   float(x["lat"]) if x.get("lat") is not None else None, float(x["lon"]) if x.get("lon") is not None else None)
            photo = save_photo(x["photo"]) if x.get("photo") else None   # 검사를 다 통과한 뒤에 저장
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            return self._json(400, {"ok": False})
        with db() as c:
            c.execute("insert into survey(at, station, bike, status, note, lat, lon, photo) values (?,?,?,?,?,?,?,?)", row + (photo,))
            n = c.execute("select count(*) from survey").fetchone()[0]
        self._json(200, {"ok": True, "total": n})

    def do_GET(self):
        if self.path.startswith("/api/survey.csv"):
            import csv, io
            with db() as c:
                rows = c.execute("select at, station, bike, status, note, lat, lon, photo from survey order by id").fetchall()
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["at", "station", "bike", "status", "note", "lat", "lon", "photo"])
            w.writerows(rows)
            body = buf.getvalue().encode("utf-8-sig")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        m = re.fullmatch(r"/api/photo/([0-9a-f]{16}\.(jpg|png))", self.path)
        if m and (photos() / m.group(1)).exists():
            body = (photos() / m.group(1)).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg" if m.group(2) == "jpg" else "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
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


def serve(port=8765, https=False):
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    if https:
        import ssl, subprocess
        tls = ROOT / "data" / "tls"
        if not (tls / "server.crt").exists():
            raise SystemExit("인증서가 없습니다: sh server/https_local.sh 를 먼저 실행하세요")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(tls / "server.crt", tls / "server.key")
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        try:   # 맥의 Bonjour 이름. 맥이 아니면 호스트 이름으로
            host = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True).stdout.strip()
        except FileNotFoundError:
            host = ""
        host = host or __import__("socket").gethostname().split(".")[0]
        print(f"https://{host}.local:{port}  (같은 와이파이의 아이폰에서)")
    else:
        print(f"http://localhost:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    serve(int(args[0]) if args else 8765, https="--https" in sys.argv)
