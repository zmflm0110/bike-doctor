// 안드로이드 앱(android-app) 아이콘·시작 화면 — web/icon.svg 하나에서 (Capacitor 기본 로고를 우리 것으로 바꿈)
//   node tools/make_android_assets.js
//   아이콘: 예전 모양(ic_launcher·round), 적응형 앞면(ic_launcher_foreground — 108dp 중 가운데 66dp 안에 그림)
//   시작 화면: res/drawable*/splash.png 크기 그대로, 남색 바탕 가운데 자전거 마크 + RIDEY 글자(민트→흰색, Y 의 민트 체크)
const fs = require("fs"), path = require("path");
const { launch } = require("../tests/web/browser");
const RES = path.resolve(__dirname, "../android-app/android/app/src/main/res");
const svg = fs.readFileSync(path.resolve(__dirname, "../web/icon.svg"), "utf8");
const defs = svg.match(/<defs>[\s\S]*?<\/defs>/)[0];
const glyph = svg.replace(/^[\s\S]*?<rect[^>]*\/>/, "").replace(/<\/svg>\s*$/, "");   // 바탕 사각형 뒤의 자전거·배지
const full = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 108 108">${defs}<rect width="108" height="108" fill="url(#g)"/><g transform="translate(21 21) scale(1.03)">${glyph}</g></svg>`;
const round = svg.replace(/<rect([^>]*?)\srx="[^"]*"/, '<rect$1 rx="32"');
const DENS = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };
(async () => {
  const browser = await launch();
  const page = await browser.newPage();
  const shot = async (html, w, h, file, transparent = false) => {
    await page.setViewportSize({ width: w, height: h });
    await page.setContent(`<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Outfit:wght@800&display=block"><style>html,body{margin:0;background:${transparent ? "transparent" : "#0B1320"}}svg{display:block}</style>${html}`);
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: file, omitBackground: transparent });
  };
  for (const [d, k] of Object.entries(DENS)) {
    const dir = path.join(RES, `mipmap-${d}`), s = Math.round(48 * k), f = Math.round(108 * k);
    await shot(svg.replace("<svg ", `<svg width="${s}" height="${s}" `), s, s, path.join(dir, "ic_launcher.png"), true);
    await shot(round.replace("<svg ", `<svg width="${s}" height="${s}" `), s, s, path.join(dir, "ic_launcher_round.png"), true);
    await shot(full.replace("<svg ", `<svg width="${f}" height="${f}" `), f, f, path.join(dir, "ic_launcher_foreground.png"));
  }
  // 시작 화면 — 기존 파일 크기 그대로
  for (const dir of fs.readdirSync(RES).filter((x) => x.startsWith("drawable"))) {
    const file = path.join(RES, dir, "splash.png");
    if (!fs.existsSync(file)) continue;
    const buf = fs.readFileSync(file); const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
    const u = Math.min(w, h) * 0.3;   // 마크 너비
    const markSvg = svg.replace(/^[\s\S]*?<rect[^>]*\/>/, "").replace(/<\/svg>\s*$/, "").replace(/<g transform="[^"]*">/, "<g>");
    await shot(`<div style="width:${w}px;height:${h}px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:${Math.round(u * 0.16)}px;background:radial-gradient(120% 80% at 50% 35%,#1d2c3a,#0B1320)">` +
      `<svg viewBox="0 0 132 92" width="${Math.round(u)}" height="${Math.round(u * 92 / 132)}" style="overflow:visible">${defs}${markSvg}</svg>` +
      `<div style="display:flex;align-items:baseline;font:800 ${Math.round(u * 0.34)}px Outfit,-apple-system,sans-serif;color:#F5F7F6">` +
      `<span style="background:linear-gradient(90deg,#35C7A0,#7fe0c4 45%,#F5F7F6);-webkit-background-clip:text;color:transparent">RIDE</span>` +
      `<svg viewBox="0 0 66 70" style="height:.7em;width:.64em;margin-left:.03em;overflow:visible"><path d="M4 3 L30 38 V68" fill="none" stroke="#F5F7F6" stroke-width="15" stroke-linejoin="round"/><path d="M36 34 L50 34 L66 3 L52 3 Z" fill="#35C7A0"/></svg></div></div>`, w, h, file);
  }
  fs.writeFileSync(path.join(RES, "values/ic_launcher_background.xml"),
    '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#0B1320</color>\n</resources>\n');
  await browser.close();
  console.log("아이콘·시작 화면 완료");
})();
