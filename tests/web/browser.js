// 브라우저 열기 — CHROME 환경변수 > 맥 개발 기기의 headless shell > Playwright 기본(리눅스 CI 는 PLAYWRIGHT_BROWSERS_PATH)
const fs = require("fs");
const { chromium } = require("playwright");
const MAC = (process.env.HOME || "") + "/Library/Caches/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-mac-arm64/chrome-headless-shell";
exports.launch = (opts = {}) => {
  const executablePath = process.env.CHROME || (fs.existsSync(MAC) ? MAC : undefined);
  return chromium.launch({ executablePath, ...opts });
};
