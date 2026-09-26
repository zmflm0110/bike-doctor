// 시연 영상 자동 녹화 (대회 제출·발표용) — 지금 목록(클라우드) → 구 고르기·정비 동선 → 조회 경고 → 3초 확인으로 순위 바뀜 → 현장 조사 → 하루 재생, 화면 아래 자막.
// 지금 목록은 진짜 클라우드(live-data)에서 받는다(인터넷 필요). 확인·조사 기록은 임시 서버 DB 로만(클라우드 DB 에 안 씀).
//   node tests/web/record_demo.js [나갈 폴더=docs/demo]   → demo.webm (ffmpeg 가 있으면 demo.mp4 도)
// 서버를 임시 DB 로 스스로 띄운다. 지도 조각이 안 받아지는 곳(오프라인)에서는 대여소 점 바탕으로 찍힌다.
const { spawn, execFileSync } = require("child_process");
const fs = require("fs"), os = require("os"), path = require("path");
const { launch } = require("./browser");
const ROOT = path.resolve(__dirname, "../..");
const OUT = path.resolve(process.argv[2] || path.join(ROOT, "docs/demo"));
const PORT = 8990 + Math.floor(Math.random() * 100);
const URL = `http://127.0.0.1:${PORT}/index.html`;
const W = 390, H = 844;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  const db = path.join(fs.mkdtempSync(path.join(os.tmpdir(), "hz-")), "t.sqlite");
  const srv = spawn(process.env.PYTHON || "python3", [path.join(ROOT, "server/app.py"), String(PORT)], { env: { ...process.env, BIKE_DB: db }, stdio: "ignore" });
  for (let i = 0; i < 50; i++) { try { await fetch(URL); break; } catch { await wait(100); } }
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "hz-video-"));
  const browser = await launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2, locale: "ko-KR", serviceWorkers: "block",
    recordVideo: { dir: tmp, size: { width: W * 2, height: H * 2 } } });
  await ctx.addInitScript(() => { window.HZ_CLOUD_OFF = true; });   // 시연 기록은 임시 DB 로
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector("#bike-list li");
  const live = (await page.$eval("#day", (d) => d.value)) === "live";
  // 자막 상자
  await page.addStyleTag({ content: `#cap{position:fixed;left:10px;right:10px;bottom:18px;z-index:9999;background:rgba(15,23,22,.88);color:#fff;
    font:600 16px/1.45 -apple-system,"Apple SD Gothic Neo","Noto Sans CJK KR",sans-serif;padding:12px 14px;border-radius:14px;transition:opacity .3s;pointer-events:none}
    #cap small{display:block;font-weight:400;opacity:.8;font-size:13px} #cap.top{top:10px;bottom:auto}` });
  // top: 시연 화면에서는 아래 숫자판을 가리지 않게 위(머리글 자리)에
  const cap = async (t, sub = "", top = false) => { await page.evaluate(([t, s, top]) => {
    let c = document.querySelector("#cap"); if (!c) { c = document.createElement("div"); c.id = "cap"; document.body.appendChild(c); }
    c.className = top ? "top" : ""; c.innerHTML = t + (s ? `<small>${s}</small>` : ""); }, [t, sub, top]); };
  const tab = (t) => page.click(`#tabs button[data-tab="${t}"]`);
  const show = (sel) => page.evaluate((sel) => { const r = document.querySelector(sel).getBoundingClientRect(); window.scrollTo({ top: window.scrollY + r.top - 130, behavior: "smooth" }); }, sel);   // 머리글 아래로 온전히
  const type = async (sel, text) => { for (const ch of text) { await page.type(sel, ch); await wait(90); } };

  await cap("따릉이 고장 신고, 귀찮아서 대부분 안 해요.", "고장 자전거는 앱에 '대여 가능' 으로 남아 다음 사람이 또 헛걸음합니다.");
  await wait(3800);
  await cap(live ? "헛걸음 제로는 서울시 공개 대여기록을 10분마다 읽어요." : "헛걸음 제로는 서울시 공개 대여기록만 봅니다.",
    "서로 다른 사람이 연달아 빌리자마자(3분·300m 안) 반납한 자전거 = 고장 의심. 센서·장비 없이.");
  await wait(4800);
  const gu = await page.$eval("#stories .story:nth-child(2)", (b) => b.dataset.gu);
  await page.click("#stories .story:nth-child(2)");
  const bike = await page.$eval("#bike-list li:last-child b", (b) => b.textContent);   // 고른 구 안, 순위 아래쪽 대여소의 자전거 — 확인하면 맨 위로 올라가는 게 보이게
  await cap(`정비 기사는 구를 골라요 — ${gu}.`, "지도와 '먼저 볼 곳' 순위. 경보의 절반이 대여소 16% 에 몰려 있어요.");
  await wait(3500);
  await show("#station-rank");
  await wait(2500);
  await page.evaluate(() => document.querySelector("#route-list").scrollIntoView({ behavior: "smooth", block: "center" }));
  const total = ((await page.textContent("#route-list li.total").catch(() => "")) || "").replace(/\s+/g, " ").trim();
  await cap("근무 시간 안에 헛걸음을 가장 많이 막는 정비 동선.", total || "붐비는 대여소를 먼저, 한산한 곳은 나중에.");
  await wait(5000);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));

  await tab("lookup");
  await cap("이용자는 빌리기 전에 번호나 QR 로 확인.", "");
  await wait(1200);
  await type("#bike-input", bike);
  await page.press("#bike-input", "Enter");
  await cap(`${bike} — 서로 다른 사람들이 바로 반납한 자전거`, "이런 자전거는 다음 사람도 35~44% 가 바로 반납해요(평소 2.5%). 옆 자전거를 고르면 헛걸음 끝.");
  await wait(5200);
  await cap("근처에 있다면 3초 확인.", "체인·타이어·안장·멀쩡함 중 한 번 탭 → 모든 폰의 정비 순위에 '사람이 확인함' 으로.");
  await wait(2200);
  await page.click("#lookup-result .choices button:has-text('체인·기어')");
  await wait(2500);
  await tab("morning");
  await page.waitForFunction(() => document.querySelector("#station-rank").textContent.includes("구조대 확인 고장"), null, { timeout: 15000 }).catch(() => {});
  await show("#station-rank");
  await cap("확인된 곳이 정비 순위 맨 위로.", "모든 폰에서 같이 바뀌어요(클라우드 DB).");
  await wait(3800);
  await page.evaluate(() => window.scrollTo({ top: 0 }));

  await tab("survey");
  await cap("현장 조사 — 사람이 본 상태를 기록해 경보가 맞았는지 잽니다.", "사진·위치와 함께 클라우드 DB 로. 인터넷이 없으면 폰에 모았다가 나중에.");
  await wait(4200);

  await tab("replay");
  await cap("2026년 6월 15일, 서울 따릉이 실제 기록을 하루 재생합니다.", "빨강 = 경보 · 초록 = 막을 수 있던 헛걸음 · 청록 = 한참 뒤에 들어온 고장 신고", true);
  await page.selectOption("#speed", "1800");
  await wait(2500);
  await page.click("#play");
  await page.waitForFunction(() => document.querySelector("#clock").textContent >= "08:00", null, { timeout: 60000 });
  await cap("출근 시간 — 경보가 켜진 자전거를 또 빌려 헛걸음한 사람들(초록).", "경보만 보여 줬어도 막을 수 있었던 헛걸음이에요.", true);
  await page.waitForFunction(() => document.querySelector("#clock").textContent >= "15:00", null, { timeout: 60000 });
  await page.selectOption("#speed", "3600");
  await cap("고장 신고는 경보보다 중앙값 20시간 늦게 들어와요.", "그 사이 한 자전거에서 평균 3.5~4.6명이 헛걸음.", true);
  await page.waitForFunction(() => document.querySelector("#clock").textContent.startsWith("다음 날"), null, { timeout: 60000 });
  await page.evaluate(() => { const s = document.querySelector("#speed"); s.insertAdjacentHTML("beforeend", '<option value="14400">4시간/초</option>'); s.value = "14400"; });
  await cap("다음 날 — 뒤늦은 고장 신고만 드문드문(청록).", "우리 경보는 이미 전날 울렸던 자전거들이에요.", true);
  await page.waitForFunction(() => document.querySelector("#play").textContent.includes("다시"), null, { timeout: 90000 });
  const n = await page.evaluate(() => ["#c-alarm", "#c-prev", "#c-fault"].map((s) => document.querySelector(s).textContent));
  await cap(`하루 동안 경보 ${n[0]} · 막을 수 있던 헛걸음 ${n[1]}명`, "서울 3개월·대전 2개월, 약 1천만 건으로 검증 · 경보는 고장 신고보다 20~25시간 먼저", true);
  await wait(5000);
  await cap("신고를 기다리지 말고, 흔적을 읽자 — 헛걸음 제로", "안드로이드·아이폰·웹 · 공개 데이터만 · 10분마다 갱신", true);
  await wait(4500);

  const video = page.video();
  await ctx.close();
  fs.mkdirSync(OUT, { recursive: true });
  const webm = path.join(OUT, "demo.webm");
  await video.saveAs(webm);   // 브라우저를 닫기 전에
  await browser.close();
  srv.kill();
  console.log("저장:", webm, (fs.statSync(webm).size / 1e6).toFixed(1) + "MB");
  const ff = process.env.FFMPEG || "ffmpeg";
  try {   // 아이폰·키노트·파워포인트용 mp4
    execFileSync(ff, ["-y", "-loglevel", "error", "-i", webm, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "28", "-preset", "slow", "-movflags", "+faststart", path.join(OUT, "demo.mp4")]);
    console.log("저장:", path.join(OUT, "demo.mp4"), (fs.statSync(path.join(OUT, "demo.mp4")).size / 1e6).toFixed(1) + "MB");
  } catch (e) { console.log("mp4 는 건너뜀 (ffmpeg 없음: FFMPEG=경로 로 지정)"); }
})();
