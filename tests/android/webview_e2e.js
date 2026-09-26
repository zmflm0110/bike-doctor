// 안드로이드 앱(에뮬레이터·디버그 APK) 안의 WebView 를 개발자 도구 프로토콜로 직접 눌러 보는 시험
//   준비: 에뮬레이터 켜고 디버그 APK 설치·실행 → PID=$(adb shell pidof kr.bikedoctor.heotgeoleumzero)
//         adb forward tcp:9333 localabstract:webview_devtools_remote_$PID
//   실행: node tests/android/webview_e2e.js
//   ※ 현장 조사(SPB-99995)·구조대 확인(목록 첫 자전거 '타이어')을 진짜 클라우드 DB 에 넣는다 — 끝나면 지울 것:
//      psql … -c "delete from survey where bike='SPB-99995'; delete from rescue where verdict='타이어' and at > now() - interval '30 minutes'"
//   2026-09-27 결과: 지금 목록·조회·번호 정리·QR 카메라·내 위치 동선·재생·현장 조사→DB·구조대 확인→DB 모두 통과.
//   (따로 확인: 사진 찍기 → 카메라 앱 → 앱에 사진 붙음, 인터넷 끊고 열면 시연 자료로, 뒤로 가기 → 홈 → 닫기)
const ok = (c, what) => console.log((c ? "  ✓ " : "  ✗ ") + what);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  const pages = await (await fetch("http://localhost:9333/json/list")).json();
  const ws = new WebSocket(pages.find((x) => x.type === "page").webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let id = 0; const wait = {}; const errs = [];
  ws.addEventListener("message", (m) => { const d = JSON.parse(m.data); if (d.id && wait[d.id]) { wait[d.id](d); delete wait[d.id]; }
    if (d.method === "Runtime.exceptionThrown") errs.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text); });
  const send = (method, params = {}) => new Promise((r) => { const i = ++id; wait[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
  const js = async (expr) => { const r = await send("Runtime.evaluate", { expression: `(async()=>{${expr}})()`, awaitPromise: true, returnByValue: true }); return r.result?.result?.value; };
  await send("Runtime.enable");
  const until = async (expr, ms = 20000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await js(`return !!(${expr})`)) return true; await sleep(500); } return false; };
  const tab = (t) => js(`document.querySelector('#tabs button[data-tab="${t}"]').click()`);
  const lookup = (v) => js(`const i=document.querySelector('#bike-input'); i.value=${JSON.stringify(v)}; i.dispatchEvent(new Event('input',{bubbles:true})); document.querySelector('#lookup-form').requestSubmit()`);

  const sum = await js(`return document.querySelector('#morning-summary').textContent.replace(/\\s+/g,' ')`);
  ok(await js(`return document.querySelector('#day').value`) === "live" && /지금 \d+대/.test(sum), "지금 목록: " + sum.slice(0, 50));
  const bike = await js(`return document.querySelector('#bike-list li b')?.textContent`);
  await tab("lookup"); await lookup(bike); await sleep(500);
  ok((await js(`return document.querySelector('#lookup-result').textContent`)).includes("피하세요"), `조회 ${bike} → 피하세요`);
  await lookup("spb 1234"); await sleep(500);
  ok((await js(`return document.querySelector('#lookup-result').textContent`)).includes("SPB-01234"), "조회: 번호 정리(spb 1234 → SPB-01234)");
  // QR 카메라
  await js(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('QR 로 찍기')).click()`);
  const camOn = await until(`(()=>{const v=document.querySelector('video'); return v && v.srcObject && v.srcObject.active && v.videoWidth>0})()`, 15000);
  ok(camOn, "QR 카메라 켜짐 " + JSON.stringify(await js(`const v=document.querySelector('video'); return v?{w:v.videoWidth,h:v.videoHeight}:null`)));
  await js(`const v=document.querySelector('video'); v&&v.srcObject&&v.srcObject.getTracks().forEach(t=>t.stop())`);
  // 위치
  await tab("morning"); await js(`document.querySelector('#route-here').click()`);
  ok(await until(`document.querySelector('#route-list').textContent.includes('내 위치에서')`, 30000), "위치: 내 위치에서 출발 동선");
  // 재생
  await tab("replay"); await sleep(1500);
  ok(await js(`return document.querySelector('#replay').offsetHeight > 200`), "재생 탭 그려짐");
  // 현장 조사 → 클라우드 DB
  await tab("survey");
  await js(`const b=document.querySelector('#survey-bike'); b.value='SPB-99995'; document.querySelector('#survey-note').value='안드로이드 시험(곧 지움)'; document.querySelector('#survey-choices button[data-st="멀쩡함"]').click()`);
  await until(`/\\d+대 기록/.test(document.querySelector('#survey-count').textContent)`, 20000);
  const cnt = await js(`return document.querySelector('#survey-count').textContent.trim()`);
  ok(/기록/.test(cnt) && !/못 보낸/.test(cnt), "현장 조사 → 클라우드 DB: " + cnt);
  // 구조대 확인 → 클라우드 DB
  await tab("lookup"); await lookup(bike); await sleep(500);
  await js(`[...document.querySelectorAll('#lookup-result .choices button')].find(b=>b.textContent.includes('타이어')).click()`);
  await until(`[...document.querySelectorAll('.toast')].some(t=>t.textContent.includes('고마워요'))`, 20000);
  const toast = await js(`return [...document.querySelectorAll('.toast')].map(t=>t.textContent).find(t=>t.includes('고마워요'))`);
  ok(/지금까지 \d+명/.test(toast || ""), "구조대 확인 → 클라우드 DB: " + (toast || "").slice(0, 50));
  ok(errs.length === 0, "화면 오류 없음" + (errs.length ? ": " + errs.join(" | ") : ""));
  console.log("BIKE=" + bike);
  ws.close();
})();
