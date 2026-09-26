// 안드로이드 앱(android-app) 아이콘·시작 화면 — web/icon.svg 하나에서 (Capacitor 기본 로고를 우리 것으로 바꿈)
//   node tools/make_android_assets.js
//   아이콘: 예전 모양(ic_launcher·round), 적응형 앞면(ic_launcher_foreground — 108dp 중 가운데 66dp 안에 그림)
//   시작 화면: res/drawable*/splash.png 크기 그대로, 청록 바탕 가운데 아이콘 + '헛걸음 제로'
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
    await page.setContent(`<style>html,body{margin:0;background:${transparent ? "transparent" : "#0f766e"}}svg{display:block}</style>${html}`);
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
    const icon = Math.round(Math.min(w, h) * 0.28);
    await shot(`<div style="width:${w}px;height:${h}px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:${Math.round(icon * 0.18)}px;background:linear-gradient(135deg,#2bb3a1,#0f766e)">` +
      `${svg.replace("<svg ", `<svg width="${icon}" height="${icon}" `)}` +
      `<div style="font:800 ${Math.round(icon * 0.26)}px -apple-system,'Apple SD Gothic Neo',sans-serif;color:#fff;letter-spacing:-0.04em">헛걸음 제로</div></div>`, w, h, file);
  }
  fs.writeFileSync(path.join(RES, "values/ic_launcher_background.xml"),
    '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">#0F766E</color>\n</resources>\n');
  await browser.close();
  console.log("아이콘·시작 화면 완료");
})();
