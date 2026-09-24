// 웹앱 다섯 탭 휴대폰 화면 검사 — 서버를 따로 띄우고(임시 DB) 탭마다 눌러 본다. 실패하면 종료 코드 1.
//   node tests/web/smoke.js            (NODE_PATH 에 playwright 가 있어야 함: npm i playwright 또는 전역 설치)
//   SHOTS=docs/shots node tests/web/smoke.js   → 탭별 화면 사진 저장
const { spawn } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");
const { launch } = require("./browser");
const ROOT = path.resolve(__dirname, "../..");
const PORT = 8790 + Math.floor(Math.random() * 100);
const URL = `http://127.0.0.1:${PORT}/index.html`;
const SHOTS = process.env.SHOTS;
const fails = [];
const check = (ok, what) => { console.log((ok ? "  ✓ " : "  ✗ ") + what); if (!ok) fails.push(what); };

(async () => {
  const db = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "hz-")), "t.sqlite");
  const srv = spawn(process.env.PYTHON || "python3", [path.join(ROOT, "server/app.py"), String(PORT)], { env: { ...process.env, BIKE_DB: db }, stdio: "ignore" });
  for (let i = 0; i < 50; i++) { try { await fetch(URL); break; } catch { await new Promise((r) => setTimeout(r, 100)); } }
  const browser = await launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: "ko-KR", serviceWorkers: "block" });
  await ctx.route(/tile\.openstreetmap\.org/, (r) => r.abort());   // 검사는 바깥 지도 조각 없이 (결과가 인터넷에 안 흔들리게)
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  page.on("dialog", (d) => { errors.push("dialog: " + d.message()); d.dismiss(); });
  const shot = async (name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + ".png") }); } };
  const tab = (t) => page.click(`#tabs button[data-tab="${t}"]`);
  try {
    await page.goto(URL, { waitUntil: "networkidle" });
    console.log("아침 목록");
    await page.waitForSelector("#bike-list li");
    check(/\d+<\/b>대가/.test(await page.innerHTML("#morning-summary")), "요약 문장");
    check((await page.$$("#station-rank li")).length === 10, "정비 순위 10곳");
    check((await page.$$("#map path.leaflet-interactive")).length > 5, "지도에 의심 대여소 표시");
    await shot("1_morning");
    const first = await page.$eval("#bike-list li b", (b) => b.textContent);

    console.log("자전거 조회");
    await tab("lookup");
    await page.fill("#bike-input", first.toLowerCase().replace("-", " "));
    await page.press("#bike-input", "Enter");
    check((await page.textContent("#lookup-result")).includes("피하세요"), `의심 자전거 경고 (${first}, 소문자·빈칸 입력)`);
    await shot("2_lookup");
    await page.fill("#bike-input", "SPB-00001");
    await page.press("#bike-input", "Enter");
    check((await page.textContent("#lookup-result")).includes("연쇄가 없어요"), "멀쩡한 자전거");
    await page.fill("#bike-input", '<img src=x onerror=alert(1)>');
    await page.press("#bike-input", "Enter");
    check((await page.$$("#lookup-result img")).length === 0 && (await page.textContent("#lookup-result")).includes("<img"), "QR·입력 속 HTML 은 글자로만");

    console.log("구조대");
    await tab("rescue");
    const target = (await page.textContent("#rescue-card h3")).split("의 ").pop();
    await page.click("#rescue-card button:has-text('타이어')");
    await page.waitForSelector(".toast");
    check((await page.textContent(".toast")).includes("1명이 이 자전거를 확인"), "제보가 서버에 들어감");
    check((await page.textContent("#rescue-log")).includes(target), "내 구조 기록");
    await shot("3_rescue");
    await tab("morning");
    await page.waitForFunction(() => document.querySelector("#station-rank").textContent.includes("구조대 확인 고장"));
    check((await page.textContent("#station-rank li")).includes("구조대 확인 고장 1대"), "확인된 곳이 정비 순위 맨 위로");
    check((await page.textContent("#bike-list")).includes(`사람 확인: 고장 1/1`), "의심 자전거에 사람 확인 표시");

    console.log("시연");
    await tab("replay");
    await page.selectOption("#speed", "3600");
    await page.click("#play");
    await page.waitForFunction(() => document.querySelector("#clock").textContent >= "09:00", null, { timeout: 20000 });
    await page.click("#play");
    const c = await page.evaluate(() => ({ alarm: +document.querySelector("#c-alarm").textContent, prev: +document.querySelector("#c-prev").textContent }));
    check(c.alarm > 20 && c.prev > 20, `재생 9시: 경보 ${c.alarm} · 막을 수 있던 헛걸음 ${c.prev}`);
    await shot("4_replay");

    console.log("현장 조사");
    await tab("survey");
    await page.fill("#station-filter", "망원");
    check((await page.$$eval("#survey-station option", (o) => o.length)) > 0, "이름으로 대여소 찾기");
    await page.fill("#survey-bike", "spb 12345");
    await page.click('#survey-choices button[data-st="체인·기어"]');
    await page.waitForFunction(() => document.querySelector("#survey-count").textContent.includes("1대"));
    const csv = await (await fetch(`http://127.0.0.1:${PORT}/api/survey.csv`)).text();
    check(csv.includes("SPB-12345") && csv.includes("체인·기어"), "조사 기록이 CSV 로");
    await shot("5_survey");
    check(errors.length === 0, "화면 오류 없음" + (errors.length ? ": " + errors.slice(0, 3).join(" | ") : ""));
  } catch (e) {
    fails.push(e.message);
    console.log("  ✗ " + e.message);
  } finally {
    await browser.close();
    srv.kill();
  }
  console.log(fails.length ? `불합격 ${fails.length}` : "합격");
  process.exit(fails.length ? 1 : 0);
})();
