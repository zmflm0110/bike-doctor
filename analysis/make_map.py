"""시연용 지도: 2026-06 경보(서로 다른 2명 연속 헛대여)를 대여소별로 세어 지도에 올린다 + 하루치 '오늘 먼저 볼 자전거' 목록.
출력: demo_map.html (로컬 파일, 브라우저로 연다)"""
import json
import numpy as np, pandas as pd

S = pd.read_excel("data/stations_2606.xlsx", header=None, skiprows=5, engine="openpyxl").iloc[:, [0, 1, 2, 4, 5]]
S.columns = ["no", "name", "gu", "lat", "lon"]
S = S.dropna(subset=["lat", "lon"])
S["st"] = S["no"].astype(int).astype(str).str.zfill(5)

R = pd.read_csv("data/rent_2606.csv", encoding="cp949",
                usecols=["자전거번호", "대여일시", "대여 대여소번호", "반납일시", "반납대여소번호", "이용거리(M)", "생년", "성별"],
                dtype={"대여 대여소번호": str, "반납대여소번호": str, "생년": "category", "성별": "category", "자전거번호": "category"})
R.columns = ["bike", "t0", "st0", "t1", "st1", "dist", "born", "sex"]
R["t0"] = pd.to_datetime(R["t0"]); R["t1"] = pd.to_datetime(R["t1"], errors="coerce")
R = R.dropna(subset=["t1"]).sort_values(["bike", "t0"]).reset_index(drop=True)
d = ((R["st0"] == R["st1"]) & ((R["t1"] - R["t0"]).dt.total_seconds() <= 120) & (R["dist"].fillna(0) < 200)).values
b = R["bike"].astype(str).values
who = (R["born"].astype(str) + R["sex"].astype(str)).values
sb = np.r_[False, b[1:] == b[:-1]]; sp = sb & np.r_[False, who[1:] == who[:-1]] & R["born"].notna().values
streak = np.zeros(len(R), dtype=np.int32)
for i in range(1, len(R)):
    if sb[i] and d[i - 1]:
        streak[i] = streak[i - 1] + (0 if sp[i] else 1)
alarm = (streak == 1) & d & ~sp
A = R.loc[alarm, ["bike", "st0", "t1"]].copy()

per = A.groupby("st0").size().rename("alarms").reset_index().rename(columns={"st0": "st"})
M = per.merge(S, on="st", how="inner").sort_values("alarms", ascending=False)
pts = [{"lat": float(r.lat), "lon": float(r.lon), "n": int(r.alarms), "name": str(r.name), "gu": str(r.gu)} for r in M.itertuples()]

day = "2026-06-15"
Ad = A[A["t1"].dt.strftime("%Y-%m-%d") == day].merge(S[["st", "name", "gu"]], left_on="st0", right_on="st", how="left")
today = [{"bike": str(x.bike), "name": str(x.name), "gu": str(x.gu), "time": x.t1.strftime("%H:%M")} for x in Ad.sort_values("t1").itertuples()]
gu = M.groupby("gu")["alarms"].sum().sort_values(ascending=False).head(10)

html = """<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>따릉이 고장 예보</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--bg:#f7f7f5;--fg:#1b1b1b;--muted:#6b6b6b;--card:#fff;--line:#e4e4e0;--hot:#d9480f}
@media (prefers-color-scheme:dark){:root{--bg:#141414;--fg:#eee;--muted:#9a9a9a;--card:#1e1e1e;--line:#333;--hot:#ff7a45}}
body{margin:0;background:var(--bg);color:var(--fg);font-family:-apple-system,"Apple SD Gothic Neo",sans-serif}
header{padding:16px}h1{font-size:20px;margin:0 0 4px}p{margin:4px 0;color:var(--muted);font-size:14px}
main{display:grid;grid-template-columns:1fr 340px;gap:12px;padding:0 16px 16px}
#map{height:72vh;border-radius:10px;border:1px solid var(--line)}
aside{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;max-height:72vh;overflow:auto}
h2{font-size:15px;margin:8px 0}li{font-size:13px;margin:3px 0}.n{color:var(--hot);font-weight:600}
@media (max-width:760px){main{grid-template-columns:1fr}#map{height:55vh}}
</style></head><body>
<header><h1>따릉이 고장 예보 — 앞사람들의 헛걸음이 곧 센서</h1>
<p>서울 공개 대여기록(2026년 6월)에서 <b>서로 다른 두 사람이 연달아 빌리자마자 반납</b>한 자전거를 찾았다. 이런 자전거는 다음 사람도 34%가 헛걸음한다(평소 2.3%).</p>
<p>원 크기 = 그 대여소에서 난 경보 수. 경보의 25%가 대여소 5.3%에 몰린다.</p></header>
<main><div id="map"></div><aside>
<h2>__DAY__ 하루 경보 __NDAY__건 — 정비 기사가 먼저 볼 자전거</h2><ol id="today"></ol>
<h2>6월 경보 많은 구</h2><ol id="gu"></ol></aside></main>
<script>
const P=__PTS__, T=__TODAY__, G=__GU__;
const map=L.map('map').setView([37.55,126.99],11);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap'}).addTo(map);
P.forEach(p=>L.circleMarker([p.lat,p.lon],{radius:Math.max(3,Math.sqrt(p.n)*2.2),color:'#d9480f',weight:1,fillOpacity:.45})
 .bindPopup(`<b>${p.name}</b><br>${p.gu} · 6월 경보 ${p.n}건`).addTo(map));
document.getElementById('today').innerHTML=T.slice(0,40).map(x=>`<li>${x.time} <span class="n">${x.bike}</span> — ${x.name} (${x.gu})</li>`).join('');
document.getElementById('gu').innerHTML=G.map(([g,n])=>`<li>${g} <span class="n">${n}</span></li>`).join('');
</script></body></html>"""
html = (html.replace("__PTS__", json.dumps(pts, ensure_ascii=False)).replace("__TODAY__", json.dumps(today, ensure_ascii=False))
        .replace("__GU__", json.dumps([[k, int(v)] for k, v in gu.items()], ensure_ascii=False))
        .replace("__DAY__", day).replace("__NDAY__", str(len(today))))
open("demo_map.html", "w").write(html)
print(f"대여소 {len(pts)}곳, {day} 경보 {len(today)}건, 구 TOP3 {list(gu.items())[:3]}")
