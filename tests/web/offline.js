// 실행: PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS=1 node tests/web/offline.js [normal|evict|notiles]
// (npm i playwright 필요. 서버를 직접 띄웠다가 검사 중 끄고, 지도 조각 주소를 막아 진짜 오프라인을 만든다 — Playwright 의 setOffline 만으로는 서비스워커 요청이 안 끊긴다)
// 오프라인 시연 검사: 한 번 열어 서비스워커가 캐시하게 한 뒤, 네트워크를 끊고 새로고침 → 시연 재생.
const { launch } = require("./browser");
const { spawn } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");
const MODE = process.argv[2] || "normal";
const PORT = 8890 + Math.floor(Math.random() * 100);
const URL = `http://localhost:${PORT}/index.html`;
(async () => {
  const db = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "hz-")), "t.sqlite");
  const srv = spawn(process.env.PYTHON || "python3", [path.resolve(__dirname, "../../server/app.py"), String(PORT)], { env: { ...process.env, BIKE_DB: db }, stdio: "ignore" });
  for (let i = 0; i < 50; i++) { try { await fetch(URL); break; } catch { await new Promise((r) => setTimeout(r, 100)); } }
  const browser = await launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  let page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text().slice(0, 120)); });
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload({ waitUntil: "networkidle" });
  console.log("온라인: SW 제어", await page.evaluate(() => !!navigator.serviceWorker.controller), "| Leaflet", await page.evaluate(() => typeof L));
  errors.length = 0;
  const cdp = await ctx.newCDPSession(page);
  if (MODE === "notiles") { await page.evaluate(() => caches.delete("hz-tiles")); await cdp.send("Network.clearBrowserCache"); console.log("지도 조각 캐시까지 비움"); }
  if (MODE === "evict") { await cdp.send("Network.clearBrowserCache"); console.log("HTTP 캐시 비움 (서비스워커 캐시는 남김)"); }
  // 진짜로 끊기: 우리 서버를 끄고(같은 출처), 지도 조각 주소는 서비스워커 요청까지 막는다(PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS=1)
  srv.kill();
  await new Promise((r) => srv.once("exit", r));
  let blocked = 0;
  await ctx.route(/tile\.openstreetmap\.org/, (r) => { blocked++; return r.abort(); });
  await ctx.setOffline(true);
  await page.close();
  page = await ctx.newPage();                      // 새 탭: 이전 탭의 메모리 속 그림이 섞이지 않게
  page.on("pageerror", (e) => errors.push("pageerror: " + e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push("console: " + m.text().slice(0, 120)); });
  await page.goto(URL, { waitUntil: "load" }).catch((e) => console.log("열기 실패:", e.message));
  await page.waitForTimeout(1500);
  console.log("오프라인: Leaflet", await page.evaluate(() => typeof L), "| jsQR", await page.evaluate(() => typeof jsQR));
  console.log("아침 목록 지도:", (await page.textContent("#map")).slice(0, 60).replace(/\s+/g, " ") || "(지도 그려짐)");
  await page.click('#tabs button[data-tab="replay"]');
  await page.selectOption("#speed", "3600");
  await page.click("#play");
  await page.waitForTimeout(4000);
  const n = await page.evaluate(() => ({ clock: document.querySelector("#clock").textContent, alarm: document.querySelector("#c-alarm").textContent,
    prev: document.querySelector("#c-prev").textContent, circles: document.querySelectorAll("#replay-map path.leaflet-interactive").length,
    stationCanvas: !!document.querySelector("#replay-map .leaflet-overlay-pane canvas"),
    tilesLoaded: [...document.querySelectorAll("#replay-map img.leaflet-tile")].filter((i) => i.complete && i.naturalWidth > 0).length }));
  console.log("시연:", JSON.stringify(n));
  await page.screenshot({ path: path.join(os.tmpdir(), "shot_offline_" + MODE + ".png") });
  console.log("막은 지도 조각 요청:", blocked);
  console.log("오류:", errors.length ? errors.slice(0, 6) : "없음");
  await browser.close();
  // 합격: 오프라인에서도 라이브러리·시연 재생이 되고, 오류는 막은 지도 조각 요청뿐
  const bad = errors.filter((e) => !/tile|ERR_FAILED|Failed to load resource/.test(e));
  if (+n.alarm <= 0 || !n.stationCanvas || bad.length) { console.log("불합격", JSON.stringify({ n, bad })); process.exit(1); }
  console.log("합격");
})();
