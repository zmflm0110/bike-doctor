// web/ 웹앱을 안드로이드 앱 안(www/)으로 복사 — 매번 새로. 실시간·운영 목록(data/live.json, data/ops)은 넣지 않는다(앱이 클라우드에서 받음).
const fs = require("fs"), path = require("path");
const SRC = path.resolve(__dirname, "../web"), DST = path.resolve(__dirname, "www");
const SKIP = new Set(["data/live.json", "data/live.tmp", "data/ops"]);
fs.rmSync(DST, { recursive: true, force: true });
(function copy(rel) {
  const s = path.join(SRC, rel), d = path.join(DST, rel);
  if (SKIP.has(rel.split(path.sep).join("/"))) return;
  if (fs.statSync(s).isDirectory()) { fs.mkdirSync(d, { recursive: true }); fs.readdirSync(s).forEach((f) => copy(path.join(rel, f))); }
  else fs.copyFileSync(s, d);
})("");
console.log("web → www:", fs.readdirSync(DST).length, "개");
