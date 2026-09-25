// 웹앱(app.js·route.js)의 답을 뽑아 아이폰 앱(Swift) 검사의 정답으로 — 두 앱이 같은 목록·순위·동선을 내는지.
//   node tests/web/parity_fixture.js   → ios/Core/Tests/HeotgeoleumCoreTests/Fixtures/parity.json
const { spawn } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");
const { launch } = require("./browser");
const ROOT = path.resolve(__dirname, "../..");
const PORT = 9090 + Math.floor(Math.random() * 100);
(async () => {
  const db = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "hz-")), "t.sqlite");
  const srv = spawn(process.env.PYTHON || "python3", [path.join(ROOT, "server/app.py"), String(PORT)], { env: { ...process.env, BIKE_DB: db }, stdio: "ignore" });
  for (let i = 0; i < 50; i++) { try { await fetch(`http://127.0.0.1:${PORT}/`); break; } catch { await new Promise((r) => setTimeout(r, 100)); } }
  const b = await launch();
  const page = await b.newPage();
  await page.goto(`http://127.0.0.1:${PORT}/index.html?day=2026-06-15`, { waitUntil: "networkidle" });
  const out = {};
  for (const day of ["2026-06-15", "2026-06-20"]) {
    await page.selectOption("#day", day);
    await page.waitForFunction((d) => state.morning && state.morning.date === d, day);
    out[day] = await page.evaluate(() => {
      const bikes = state.morning.bikes;
      const rank = groupByStation(bikes).map(([id, arr]) => ({ id, bikes: arr.map((x) => x.bike) }));
      const top = groupByStation(bikes).slice(0, 10).map(([id]) => ({ id, ...state.stations[id] }));
      const stops = planRoute(top[0], top.slice(1));
      const here = { lat: 37.5556, lon: 126.9106 };
      const near = groupByStation(bikes).map(([id]) => ({ id, ...state.stations[id] })).filter((s) => s.lat)
        .sort((a, c) => meters(here, a) - meters(here, c)).slice(0, 10);
      const nearStops = planRoute(here, near);
      const known = bikes.filter((x) => typeof x.truth_first_rider_dud === "boolean");
      const gu = {}; bikes.forEach((x) => (gu[guOf(x)] = (gu[guOf(x)] || 0) + 1));
      // 막는 동선: 9시 출발, 서울 전체·송파구 × 1시간·1시간 반·3시간 (renderRoute 와 같은 규칙)
      const valueRoutes = {};
      for (const gu of ["", "송파구"]) for (const minutes of [60, 90, 180]) {
        const bs = gu ? bikes.filter((x) => guOf(x) === gu) : bikes;
        const cands = groupByStation(bs).map(([id, arr]) => ({ id, arr, n: arr.length, ...state.stations[id] })).filter((s) => s.lat)
          .sort((a, c) => stationValue(c, 540) - stationValue(a, 540)).slice(0, 40);
        const p = planValue(cands[0], cands, stationValue, minutes, 540);
        valueRoutes[`${gu || "전체"}/${minutes}`] = { stops: p.map((s) => s.id), value: simulate(cands[0], p, stationValue, 540).value };
      }
      return { rank, valueRoutes, route: [top[0].id, ...stops.map((s) => s.id)], routeMeters: pathLength(top[0], stops),
        nearRoute: nearStops.map((s) => s.id), nearMeters: pathLength(here, nearStops),
        retro: { known: known.length, hit: known.filter((x) => x.truth_first_rider_dud).length }, gu };
    });
  }
  out.lookup = ["spb 69683", "SPB69683", "spb-1234", "  SPB - 00012 ", "hello"].map((raw) => {
    const m = String(raw).toUpperCase().match(/SPB-?\s?(\d{3,6})/);
    return [raw, m ? `SPB-${m[1].padStart(5, "0")}` : null];
  });
  await b.close(); srv.kill();
  const file = path.join(ROOT, "ios/Core/Tests/HeotgeoleumCoreTests/Fixtures/parity.json");
  fs.writeFileSync(file, JSON.stringify(out, null, 1));
  console.log("→", file, Object.keys(out));
})();
