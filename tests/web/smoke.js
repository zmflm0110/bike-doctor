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
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, locale: "ko-KR", serviceWorkers: "block",
    permissions: ["geolocation"], geolocation: { latitude: 37.5556, longitude: 126.9106 } });   // 망원역 앞에 서 있다고
  await ctx.route(/tile\.openstreetmap\.org/, (r) => r.abort());   // 검사는 바깥 지도 조각 없이 (결과가 인터넷에 안 흔들리게)
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text()); });
  page.on("dialog", (d) => { errors.push("dialog: " + d.message()); d.dismiss(); });
  const shot = async (name) => { if (SHOTS) { fs.mkdirSync(SHOTS, { recursive: true }); await page.screenshot({ path: path.join(SHOTS, name + ".png") }); } };
  const tab = (t) => page.click(`#tabs button[data-tab="${t}"]`);
  // 글자 대비 (WCAG AA 4.5:1) — 보이는 탭·머리글·탭 단추에서 기준 못 넘는 글자
  const lowContrast = () => page.evaluate(() => {
        const lum = (c) => { const v = c.match(/[\d.]+/g).slice(0, 3).map((x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
        const bg = (el) => { for (; el; el = el.parentElement) { const c = getComputedStyle(el).backgroundColor; if (c && !/^rgba\(.*,\s*0\)$/.test(c) && c !== "transparent") return c; /* 투명(rgba ..., 0)만 건너뜀 — 예전 식은 검정 rgb(0, 0, 0) 도 투명으로 봤음 */ } return "rgb(255,255,255)"; };
        return [...document.querySelectorAll(".tab.on *, header *, nav *")].filter((el) => el.offsetParent &&
          [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())).map((el) => {
          const a = lum(getComputedStyle(el).color), b = lum(bg(el));
          return [(Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05), el.textContent.trim().slice(0, 12)]; }).filter(([r]) => r < 4.5);
      });

  try {
    await page.goto(URL + "?day=2026-06-15", { waitUntil: "networkidle" });   // 시연 날짜로 고정 (실시간 서버가 도는 맥에선 기본이 '지금' 이 됨)
    console.log("아침 목록");
    await page.waitForSelector("#bike-list li");
    check(/\d+<\/b>대가/.test(await page.innerHTML("#morning-summary")), "요약 문장");
    check((await page.$$("#station-rank li")).length === 10, "정비 순위 10곳");
    check((await page.$$("#map path.leaflet-interactive")).length > 5, "지도에 의심 대여소 표시");
    const retro = await page.textContent("#morning-retro");
    check(/처음 빌린 사람 \d+명 중 \d+명\(\d+%\)/.test(retro), "뒤돌아 채점: " + retro.match(/\d+명 중 \d+명\(\d+%\)/)?.[0]);
    const route = await page.$$eval("#route-list li", (li) => li.map((x) => x.textContent));
    const total = route[route.length - 1] || "";
    const m90 = total.match(/(\d+)곳 · 약 (\d+)분 · 막을 헛걸음 예상 ([\d.]+)명/);
    check(m90 && +m90[1] === route.length - 1 && +m90[2] <= 90, "막는 동선 1시간 30분: " + (m90 ? m90[0] : total.trim()));
    check((await page.$$("#map .route-num")).length === route.length - 1, "지도에 동선 번호");
    await page.selectOption("#shift", "180");
    const m180 = (await page.textContent("#route-list li.total")).match(/막을 헛걸음 예상 ([\d.]+)명/);
    check(m180 && m90 && +m180[1] >= +m90[3], `근무 3시간이면 더 막음 (${m90 && m90[3]} → ${m180 && m180[1]}명)`);
    await page.selectOption("#shift", "90");
    await shot("1_morning");
    await page.click("#route-here");
    await page.waitForFunction(() => document.querySelector("#route-list").textContent.includes("내 위치에서"));
    check(true, "내 위치에서 출발");
    await page.evaluate(() => window.scrollTo(0, 0));
    // 구 고르기 + 정비 담당용 CSV
    const opt = await page.$$eval("#gu option", (o) => o.map((x) => [x.value, x.textContent]));
    const [gu, label] = opt.slice(1).sort((a, b) => +b[1].match(/\((\d+)대/)[1] - +a[1].match(/\((\d+)대/)[1])[0];
    const nGu = +label.match(/\((\d+)대/)[1];
    await page.selectOption("#gu", gu);
    const inList = await page.$$eval("#bike-list li", (li) => li.length);
    check(inList === Math.min(nGu, 80) && (await page.textContent("#morning-summary")).startsWith(gu), `${gu} 만 보기 (${nGu}대)`);
    const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#csv-btn")]);
    const csvText = fs.readFileSync(await dl.path(), "utf8");
    const lines = csvText.replace(/^\ufeff/, "").trim().split("\r\n");
    check(csvText.startsWith("\ufeff") && lines.length === nGu + 1 && lines.slice(1).every((l) => l.includes(`"${gu}"`)) && /^morning_2026-\d\d-\d\d_[a-z]+\.csv$/.test(dl.suggestedFilename()),
      `CSV ${dl.suggestedFilename()} (${lines.length - 1}줄, 엑셀용 BOM)`);
    await page.selectOption("#gu", "");
    // 아이폰: 입력칸 글자가 16px 보다 작으면 누를 때 화면이 확대된다, 홈 화면 아이콘은 PNG 여야 한다
    const small = await page.$$eval("input,select", (els) => els.filter((e) => e.type !== "file" && parseFloat(getComputedStyle(e).fontSize) < 16).map((e) => e.id));
    check(small.length === 0, "입력칸 글자 16px 이상 (아이폰 확대 방지)" + (small.length ? ": " + small : ""));
    const touch = await page.$eval('link[rel="apple-touch-icon"]', (l) => l.href);
    const icon = await fetch(touch);
    check(icon.ok && icon.headers.get("content-type") === "image/png", "홈 화면 아이콘 PNG");
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
    await page.click("#rescue-near");
    await page.waitForFunction(() => /\d+(m|\.\dkm)$/.test(document.querySelector("#rescue-card h3").textContent));
    const near = await page.textContent("#rescue-card h3");
    check(/(\d+m|\d\.\dkm)$/.test(near), "가까운 의심 자전거부터: " + near);
    const target = near.split("의 ").pop().split(" · ")[0];
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
    // 사진: 폰 카메라 대신 큰 그림 파일(3000×2000)을 넣어 줄여 보내는지
    const big = await page.evaluate(() => { const c = document.createElement("canvas"); c.width = 3000; c.height = 2000;
      const g = c.getContext("2d"); g.fillStyle = "#0f766e"; g.fillRect(0, 0, 3000, 2000); g.fillStyle = "#fff"; g.fillRect(900, 600, 1200, 800);
      return c.toDataURL("image/png").split(",")[1]; });
    await page.setInputFiles("#survey-photo", { name: "bike.png", mimeType: "image/png", buffer: Buffer.from(big, "base64") });
    await page.waitForFunction(() => !document.querySelector("#survey-thumb").hidden);
    await page.click('#survey-choices button[data-st="체인·기어"]');
    await page.waitForFunction(() => document.querySelector("#survey-count").textContent.includes("1대"));
    const csv = await (await fetch(`http://127.0.0.1:${PORT}/api/survey.csv`)).text();
    check(csv.includes("SPB-12345") && csv.includes("체인·기어"), "조사 기록이 CSV 로");
    const photo = csv.trim().split("\n").pop().trim().split(",").pop();
    const pr = await fetch(`http://127.0.0.1:${PORT}/api/photo/${photo}`);
    const pb = Buffer.from(await pr.arrayBuffer());
    check(pr.ok && pb[0] === 0xff && pb[1] === 0xd8 && pb.length < 300000, `사진이 줄어 JPEG 로 저장 (${Math.round(pb.length / 1024)}KB)`);
    check(await page.$eval("#survey-thumb", (i) => i.hidden), "저장 뒤 사진 칸 비움");
    await shot("5_survey");
    await page.goto(URL + "?day=2026-06-20", { waitUntil: "networkidle" });
    check(await page.$eval("#day", (d) => d.value) === "2026-06-20", "주소의 ?day= 로 날짜 고르기");
    console.log("글자 대비 (다섯 탭 × 밝은·어두운 화면)");
    const low = [];
    for (const cs of ["light", "dark"]) {
      await page.emulateMedia({ colorScheme: cs });
      for (const t of ["morning", "lookup", "rescue", "replay", "survey"]) { await tab(t); (await lowContrast()).forEach((x) => low.push([cs, t, ...x])); }
    }
    check(low.length === 0, "4.5:1 이상" + (low.length ? ": " + JSON.stringify(low.slice(0, 4)) : ""));
    console.log("실시간 — 서울 자료가 늦을 때");
    const st = JSON.parse(fs.readFileSync(path.join(ROOT, "web/data/stations.json")))[0];
    const kst = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 19);
    const live = { date: "live", at: kst, rule: "시험", today_alarms: 3, score: {}, rentals_in_window: 1,
      bikes: [{ bike: "SPB-54321", station: st.id, station_name: st.name, chain: 3, level: "빨강", last_dud: "09-25 13:40", minutes_ago: 5, reported: null }],
      feed: { ok: false, since: kst.slice(0, 11) + "14:00", ratio: 0.023 } };
    await page.route(/data\/live\.json/, (r) => r.fulfill({ contentType: "application/json", body: JSON.stringify(live) }));
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto(URL, { waitUntil: "networkidle" });
    await page.waitForFunction(() => document.querySelector("#morning-summary").textContent.includes("지금"));
    const note = await page.textContent("#morning-summary .feed-note").catch(() => "");
    check(/14시부터 평소의 2%만/.test(note), "자료 지연 알림: " + (note.match(/\d+시부터 평소의 \d+%만/) || [""])[0]);
    await tab("lookup"); await page.fill("#bike-input", "SPB-11111"); await page.press("#bike-input", "Enter");
    check(!!(await page.$("#lookup-result .feed-note")), "조회 '연쇄 없음' 에도 지연 알림");
    live.feed = { ok: true }; await page.goto(URL, { waitUntil: "networkidle" });
    await page.waitForFunction(() => document.querySelector("#morning-summary").textContent.includes("지금"));
    check(!(await page.$("#morning-summary .feed-note")), "자료가 정상이면 알림 없음");
    await page.unroute(/data\/live\.json/);
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
