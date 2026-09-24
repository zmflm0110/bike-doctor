// 오프라인에서도 시연·목록이 뜨게. 먼저 새로 받고(개발 중 옛 파일이 남지 않게), 안 되면 캐시.
// 지도 라이브러리(Leaflet·jsQR)는 web/vendor 에 두어 같이 캐시한다 — CDN 은 브라우저 HTTP 캐시가 비면 오프라인에서 사라졌다.
const CACHE = "hz-v4";
const TILES = "hz-tiles";   // 실제로 본 지도 조각만 (미리 대량으로 받지 않음 — OSM 지도 조각 이용 정책)
const MAX_TILES = 500;
const SHELL = ["./", "index.html", "style.css", "app.js", "icon.svg", "manifest.webmanifest",
  "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/jsqr/jsQR.js",
  "data/stations.json", "data/morning/index.json", "data/replay_2026-06-15.json", "data/morning/2026-06-15.json"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL))));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE && k !== TILES).map((k) => caches.delete(k))))));

async function trim(c) {
  const ks = await c.keys();
  if (ks.length > MAX_TILES) await Promise.all(ks.slice(0, ks.length - MAX_TILES).map((k) => c.delete(k)));
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.hostname.endsWith("tile.openstreetmap.org")) {   // 저장된 조각을 먼저 보여 주고, 뒤에서 새로 받아 바꿔 둔다
    e.respondWith(caches.open(TILES).then(async (c) => {
      const hit = await c.match(e.request);
      const net = fetch(e.request).then((r) => { if (r.ok) { c.put(e.request, r.clone()).then(() => trim(c)); } return r; }).catch(() => hit || Response.error());
      return hit || net;
    }));
    return;
  }
  if (url.origin !== location.origin) return;
  e.respondWith(fetch(e.request).then((r) => {
    const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return r;
  }).catch(() => caches.match(e.request)));
});
