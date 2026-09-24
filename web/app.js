// 헛걸음 제로 — 아침 목록(어제까지 기록), 자전거 조회, 구조대, 시연.
const $ = (s) => document.querySelector(s);
const state = { stations: {}, day: null, morning: null, map: null, layer: null };

async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

// ── 탭
document.querySelectorAll("#tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.id === b.dataset.tab));
    if (b.dataset.tab === "morning" && state.map) setTimeout(() => state.map.invalidateSize(), 50);
    if (b.dataset.tab === "rescue") renderRescue();
  })
);

// ── 아침 목록
async function loadDay(day) {
  state.day = day;
  state.morning = await getJSON(`data/morning/${day}.json`);
  const bikes = state.morning.bikes;
  const red = bikes.filter((b) => b.level === "빨강").length;
  const unrep = bikes.filter((b) => !b.reported).length;
  $("#morning-summary").innerHTML =
    `<b>${bikes.length}</b>대가 어제까지 서로 다른 사람들이 빌리자마자 반납한 채로 남아 있어요 ` +
    `(빨강 ${red}대). 이 중 <b>${unrep}</b>대는 아직 아무도 고장 신고를 안 했어요.`;
  renderMap(bikes);
  renderRank(bikes);
  $("#bike-list").innerHTML = bikes.slice(0, 80).map(bikeRow).join("");
  renderRescue();
}

function bikeRow(b) {
  return `<li><div><b>${b.bike}</b> <span class="muted">${b.station_name}</span><br>` +
    `<span class="muted">서로 다른 ${b.chain}명 연속 · 마지막 ${b.last_dud}${b.reported ? " · 신고됨" : " · <b>미신고</b>"}</span></div>` +
    `<span class="tag ${b.level}">${b.level}</span></li>`;
}

function groupByStation(bikes) {
  const g = {};
  bikes.forEach((b) => (g[b.station] = g[b.station] || []).push(b));
  // 우선순위 = 연쇄 길이의 합 (그만큼 사람들이 이미 헛걸음했고, 앞으로도 날 가능성이 큼)
  return Object.entries(g).sort((a, b) => sumChain(b[1]) - sumChain(a[1]) || b[1].length - a[1].length);
}
const maxChain = (arr) => Math.max(...arr.map((b) => b.chain));
const sumChain = (arr) => arr.reduce((t, b) => t + b.chain, 0);

function renderRank(bikes) {
  $("#station-rank").innerHTML = groupByStation(bikes).slice(0, 10).map(([id, arr]) => {
    const s = state.stations[id];
    return `<li><div><b>${s ? s.name : id}</b><br><span class="muted">${s ? s.gu : ""} · 의심 ${arr.length}대 · 헛걸음 ${sumChain(arr)}명 누적 (최대 ${maxChain(arr)}명 연속)</span></div>` +
      `<span class="tag ${arr.some((b) => b.level === "빨강") ? "빨강" : "노랑"}">${arr.length}</span></li>`;
  }).join("");
}

function renderMap(bikes) {
  if (typeof L === "undefined") { $("#map").textContent = "지도를 불러오지 못했어요(오프라인). 아래 목록을 보세요."; return; }
  if (!state.map) {
    state.map = L.map("map").setView([37.55, 126.99], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: "© OpenStreetMap" }).addTo(state.map);
  }
  if (state.layer) state.layer.remove();
  state.layer = L.layerGroup().addTo(state.map);
  groupByStation(bikes).forEach(([id, arr]) => {
    const s = state.stations[id];
    if (!s) return;
    const red = arr.some((b) => b.level === "빨강");
    L.circleMarker([s.lat, s.lon], { radius: 5 + 2 * arr.length, color: red ? "#d9480f" : "#d99a06", weight: 1, fillOpacity: 0.55 })
      .bindPopup(`<b>${s.name}</b><br>${arr.map((b) => `${b.bike} · ${b.chain}명 연속`).join("<br>")}`)
      .addTo(state.layer);
  });
}

// ── 자전거 조회
function lookup(raw) {
  const m = String(raw).toUpperCase().match(/SPB-?\s?(\d{3,6})/);
  const id = m ? `SPB-${m[1].padStart(5, "0")}` : String(raw).trim().toUpperCase();
  const hit = state.morning.bikes.find((b) => b.bike === id);
  const out = $("#lookup-result");
  if (hit) {
    out.innerHTML = `<div class="result warn"><h3>⚠︎ ${id} 는 피하세요</h3>` +
      `어제까지 <b>서로 다른 ${hit.chain}명</b>이 이 자전거를 빌리자마자 반납했어요 (마지막 ${hit.last_dud}, ${hit.station_name}).<br>` +
      `이런 자전거는 다음 사람도 ${hit.level === "빨강" ? "약 70%" : "약 35~55%"}가 바로 반납했어요. 옆 자전거를 고르세요.` +
      `<div class="choices"><button onclick="rescueSave('${id}','체인·기어')">체인·기어 문제</button><button onclick="rescueSave('${id}','타이어')">타이어</button>` +
      `<button onclick="rescueSave('${id}','안장·핸들')">안장·핸들</button><button class="fine" onclick="rescueSave('${id}','멀쩡함')">멀쩡해 보여요</button></div></div>`;
  } else {
    out.innerHTML = `<div class="result ok"><h3>✓ ${id}</h3>어제까지 기록에 헛걸음 연쇄가 없어요.</div>`;
  }
}
$("#lookup-form").addEventListener("submit", (e) => { e.preventDefault(); lookup($("#bike-input").value); });

let scanning = false;
$("#scan-btn").addEventListener("click", async () => {
  const video = $("#cam"), canvas = $("#cam-canvas");
  if (scanning) { stopScan(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    video.srcObject = stream; video.hidden = false; await video.play(); scanning = true;
    $("#scan-btn").textContent = "그만 찍기";
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    const tick = () => {
      if (!scanning) return;
      if (video.readyState === video.HAVE_ENOUGH_DATA) {
        canvas.width = video.videoWidth; canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0);
        const code = window.jsQR && jsQR(ctx.getImageData(0, 0, canvas.width, canvas.height).data, canvas.width, canvas.height);
        if (code) { stopScan(); $("#bike-input").value = code.data; lookup(code.data); return; }
      }
      requestAnimationFrame(tick);
    };
    tick();
  } catch (err) {
    $("#lookup-result").innerHTML = `<div class="result">카메라를 쓸 수 없어요(${err.name}). 번호를 직접 넣어 주세요.</div>`;
  }
});
function stopScan() {
  scanning = false;
  const v = $("#cam");
  if (v.srcObject) v.srcObject.getTracks().forEach((t) => t.stop());
  v.hidden = true; $("#scan-btn").textContent = "QR 로 찍기";
}

// ── 구조대 (지금은 이 기기에만 저장 — Phase 3 서버가 생기면 전송)
function rescueLog() { try { return JSON.parse(localStorage.getItem("rescue") || "[]"); } catch { return []; } }
window.rescueSave = (bike, verdict) => {
  const log = rescueLog();
  log.unshift({ bike, verdict, at: new Date().toLocaleString("ko-KR"), day: state.day });
  try { localStorage.setItem("rescue", JSON.stringify(log.slice(0, 200))); } catch {}
  renderRescue();
  $("#lookup-result").innerHTML += `<div class="result ok">고마워요! "${verdict}" 로 기록했어요.</div>`;
};
function renderRescue() {
  if (!state.morning) return;
  const done = new Set(rescueLog().filter((x) => x.day === state.day).map((x) => x.bike));
  const next = state.morning.bikes.find((b) => !done.has(b.bike));
  $("#rescue-card").innerHTML = next
    ? `<div class="result warn"><h3>${next.station_name}의 ${next.bike}</h3>서로 다른 ${next.chain}명이 바로 반납했어요. 가까이 있다면 3초만 봐 주세요.` +
      `<div class="choices"><button onclick="rescueSave('${next.bike}','체인·기어')">체인·기어</button><button onclick="rescueSave('${next.bike}','타이어')">타이어</button>` +
      `<button onclick="rescueSave('${next.bike}','안장·핸들')">안장·핸들</button><button class="fine" onclick="rescueSave('${next.bike}','멀쩡함')">멀쩡해요</button></div></div>`
    : `<div class="result ok">오늘 목록을 다 확인했어요!</div>`;
  $("#rescue-log").innerHTML = rescueLog().slice(0, 20).map((x) =>
    `<li><div><b>${x.bike}</b><br><span class="muted">${x.at}</span></div><span class="tag ${x.verdict === "멀쩡함" ? "ok" : "빨강"}">${x.verdict}</span></li>`).join("");
}

// ── 시연
let replay = null, timer = null;
async function startReplay() {
  if (!replay) replay = await getJSON("data/replay_2026-06-15.json");
  if (timer) { clearInterval(timer); timer = null; $("#play").textContent = "▶ 재생"; return; }
  let clock = 0, i = 0;
  const c = { 헛대여: 0, 경보: 0, "막을 수 있던 헛걸음": 0, "고장 신고": 0 };
  const feed = $("#replay-feed"); feed.innerHTML = "";
  const secs = (e) => e.s;   // 그날 0시부터 초 (다음 날 신고는 86400 넘음)
  $("#play").textContent = "■ 멈춤";
  timer = setInterval(() => {
    clock += +$("#speed").value / 10;
    while (i < replay.events.length && secs(replay.events[i]) <= clock) {
      const e = replay.events[i++];
      c[e.type] = (c[e.type] || 0) + 1;
      if (e.type !== "헛대여") {
        const s = state.stations[e.station];
        const text = e.type === "고장 신고" ? `${e.t} 고장 신고 들어옴 — ${e.bike} (${e.kind}) · 우리 경보는 이미 울렸음`
          : e.type === "경보" ? `${e.t} 경보 — ${e.bike} 서로 다른 ${e.chain}명 연속 (${s ? s.name : e.station})`
          : `${e.t} 막을 수 있던 헛걸음 — ${e.bike} (${s ? s.name : e.station})`;
        feed.insertAdjacentHTML("afterbegin", `<li class="${e.type.split(" ")[0]}">${text}</li>`);
      }
    }
    const h = Math.min(24, Math.floor(clock / 3600)), m = Math.floor((clock % 3600) / 60);
    $("#clock").textContent = (clock >= 86400 ? "다음 날 " : "") + `${String(Math.floor(clock / 3600) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    $("#c-dud").textContent = c["헛대여"] + c["경보"] + c["막을 수 있던 헛걸음"];
    $("#c-alarm").textContent = c["경보"];
    $("#c-prev").textContent = c["막을 수 있던 헛걸음"];
    $("#c-fault").textContent = c["고장 신고"];
    if (i >= replay.events.length) { clearInterval(timer); timer = null; $("#play").textContent = "▶ 다시"; }
  }, 100);
}
$("#play").addEventListener("click", startReplay);

// ── 시작
(async () => {
  const list = await getJSON("data/stations.json");
  list.forEach((s) => (state.stations[s.id] = s));
  const days = await getJSON("data/morning/index.json");
  $("#day").innerHTML = days.map((d) => `<option ${d === "2026-06-15" ? "selected" : ""}>${d}</option>`).join("");
  $("#day").addEventListener("change", (e) => loadDay(e.target.value));
  await loadDay($("#day").value);
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
})();
