// 시연 영상 자동 녹화 (대회 제출·발표용) — 아침 목록 → 자전거 조회 경고 → 구조대 → 하루 재생, 화면 아래 자막.
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
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector("#bike-list li");
  // 자막 상자
  await page.addStyleTag({ content: `#cap{position:fixed;left:10px;right:10px;bottom:18px;z-index:9999;background:rgba(15,23,22,.88);color:#fff;
    font:600 16px/1.45 -apple-system,"Apple SD Gothic Neo","Noto Sans CJK KR",sans-serif;padding:12px 14px;border-radius:14px;transition:opacity .3s}
    #cap small{display:block;font-weight:400;opacity:.8;font-size:13px} #cap.top{top:10px;bottom:auto}` });
  // top: 시연 화면에서는 아래 숫자판을 가리지 않게 위(머리글 자리)에
  const cap = async (t, sub = "", top = false) => { await page.evaluate(([t, s, top]) => {
    let c = document.querySelector("#cap"); if (!c) { c = document.createElement("div"); c.id = "cap"; document.body.appendChild(c); }
    c.className = top ? "top" : ""; c.innerHTML = t + (s ? `<small>${s}</small>` : ""); }, [t, sub, top]); };
  const tab = (t) => page.click(`#tabs button[data-tab="${t}"]`);
  const type = async (sel, text) => { for (const ch of text) { await page.type(sel, ch); await wait(90); } };

  await cap("따릉이 고장 신고, 귀찮아서 대부분 안 해요.", "그래서 고장 자전거는 '대여 가능' 으로 남아 다음 사람이 또 헛걸음합니다.");
  await wait(3500);
  const bike = await page.$eval("#bike-list li b", (b) => b.textContent);
  await cap("헛걸음 제로는 어제까지의 공개 대여기록만 봅니다.", "서로 다른 사람이 연달아 3분 안에 반납한 자전거 = 고장 의심. 그중 대부분은 아직 신고도 없어요.");
  await wait(4500);
  await cap("이 목록은 맞았을까? — 지난 기록이라 채점할 수 있어요.", (await page.textContent("#morning-retro")).replace("이 목록은 맞았을까? (지난 기록이라 채점할 수 있어요) ", ""));
  await wait(5000);
  await page.evaluate(() => window.scrollTo({ top: 520, behavior: "smooth" }));
  await cap("정비 기사는 '먼저 볼 곳' 부터.", "누적 헛걸음이 많은 대여소 순서 — 경보의 절반이 대여소 16% 에 몰려 있어요.");
  await wait(4000);
  await page.evaluate(() => document.querySelector("#route-list").scrollIntoView({ behavior: "smooth", block: "center" }));
  await cap("도는 순서까지 — 정비 동선.", "위치를 켜면 내 근처 의심 대여소 10곳을 도는 순서와 거리.");
  await wait(4000);
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));

  await tab("lookup");
  await cap("이용자는 빌리기 전에 번호나 QR 로 확인.", "");
  await wait(1200);
  await type("#bike-input", bike);
  await page.press("#bike-input", "Enter");
  await cap(`${bike} — 어제 서로 다른 사람들이 바로 반납한 자전거`, "이런 자전거는 다음 사람도 35~70% 가 포기해요(평소 2.5%). 옆 자전거를 고르면 헛걸음 끝.");
  await wait(5000);

  await tab("rescue");
  await cap("근처에 있다면 3초 구조대.", "체인·타이어·안장·멀쩡함 중 한 번 탭 → 정비 순위에 '사람이 확인함' 으로 올라갑니다.");
  await wait(2500);
  await page.click("#rescue-card button:has-text('체인·기어')");
  await wait(3000);
  await tab("morning");
  await page.waitForFunction(() => document.querySelector("#station-rank").textContent.includes("구조대 확인 고장")).catch(() => {});
  await page.evaluate(() => document.querySelector("#station-rank").scrollIntoView({ behavior: "smooth", block: "start" }));
  await cap("구조대가 확인한 곳이 정비 순위 맨 위로.", "");
  await wait(3500);
  await page.evaluate(() => window.scrollTo({ top: 0 }));

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
  await cap(`하루 동안 경보 ${n[0]} · 막을 수 있던 헛걸음 ${n[1]}명`, "신고를 기다리지 말고, 흔적을 읽자 — 헛걸음 제로", true);
  await wait(5000);

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
