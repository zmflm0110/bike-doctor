// 오프라인에서도 시연·목록이 뜨게. 먼저 새로 받고(개발 중 옛 파일이 남지 않게), 안 되면 캐시.
const CACHE = "hz-v2";
const SHELL = ["./", "index.html", "style.css", "app.js", "icon.svg", "manifest.webmanifest",
  "data/stations.json", "data/morning/index.json", "data/replay_2026-06-15.json", "data/morning/2026-06-15.json"];
self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL))));
self.addEventListener("activate", (e) => e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))));
self.addEventListener("fetch", (e) => {
  if (new URL(e.request.url).origin !== location.origin) return;
  e.respondWith(fetch(e.request).then((r) => {
    const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); return r;
  }).catch(() => caches.match(e.request)));
});
