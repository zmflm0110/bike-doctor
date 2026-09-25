// 제출용 PDF 만들기: 발표(docs/slides.html → slides.pdf), 보고서·제안서(docs/report.md·proposal.md → .pdf)
//   npm i playwright marked && node docs/build_pdf.js
// 인터넷 없이 된다(그림은 docs/ 안의 파일). 한글 글꼴은 기기에 있는 것(맥: Apple SD Gothic Neo, 리눅스: Noto Sans CJK).
const fs = require("fs"), path = require("path");
const { marked } = require("marked");
const { launch } = require("../tests/web/browser");
const DOCS = __dirname;

const CSS = `
  @page { size: A4; margin: 18mm 16mm; }
  body { font-family: -apple-system, "Apple SD Gothic Neo", "Pretendard", "Noto Sans CJK KR", "Noto Sans KR", sans-serif;
         color: #17201f; font-size: 10.5pt; line-height: 1.6; max-width: 820px; margin: 0 auto; }
  h1 { font-size: 22pt; margin: 0 0 4px; letter-spacing: -0.5px; } h1 + h3 { margin-top: 0; color: #5d6b69; font-weight: 500; }
  h2 { font-size: 15pt; border-bottom: 2px solid #0f766e; padding-bottom: 4px; margin-top: 26px; break-after: avoid; }
  h3 { font-size: 12pt; margin-top: 18px; break-after: avoid; }
  blockquote { margin: 12px 0; padding: 10px 14px; background: #eef7f5; border-left: 4px solid #0f766e; }
  table { border-collapse: collapse; margin: 8px 0; font-size: 9.5pt; break-inside: avoid; }
  th, td { border: 1px solid #dfe5e3; padding: 4px 8px; } th { background: #f1f4f3; }
  img { max-width: 100%; break-inside: avoid; }
  code { font-size: 9pt; background: #f1f4f3; padding: 1px 4px; border-radius: 4px; }
  .foot { margin-top: 30px; color: #5d6b69; font-size: 8.5pt; }`;

(async () => {
  const browser = await launch();
  const page = await browser.newPage();
  for (const [name, title] of [["report", "헛걸음 제로 — 보고서"], ["proposal", "헛걸음 제로 — 서울시설공단 제안서"]]) {
    const md = fs.readFileSync(path.join(DOCS, name + ".md"), "utf8").replace(/\s*\(초안\)/, "").replace(/(?<!\\)~/g, "\\~");   // 12~23% 가 취소선으로 바뀌지 않게
    const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>${title}</title><style>${CSS}</style></head><body>` +
      marked.parse(md) + `<p class="foot">코드·자료 재현: README.md · 만든 날 ${new Date().toISOString().slice(0, 10)}</p></body></html>`;
    fs.writeFileSync(path.join(DOCS, name + ".html"), html);
    await page.goto("file://" + path.join(DOCS, name + ".html"), { waitUntil: "load" });
    await page.pdf({ path: path.join(DOCS, name + ".pdf"), format: "A4", printBackground: true,
      displayHeaderFooter: true, headerTemplate: "<span></span>",
      footerTemplate: '<div style="font-size:8px;width:100%;text-align:center;color:#888"><span class="pageNumber"></span> / <span class="totalPages"></span></div>' });
  }
  await page.goto("file://" + path.join(DOCS, "slides.html"), { waitUntil: "load" });
  await page.emulateMedia({ media: "print" });
  await page.pdf({ path: path.join(DOCS, "slides.pdf"), width: "1280px", height: "720px", printBackground: true, preferCSSPageSize: true });
  await browser.close();
  for (const f of ["report.pdf", "proposal.pdf", "slides.pdf"]) console.log(f, (fs.statSync(path.join(DOCS, f)).size / 1e6).toFixed(1) + "MB");
})();
