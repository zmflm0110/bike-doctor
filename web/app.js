// 헛걸음 제로 — 아침 목록(어제까지 기록), 자전거 조회, 구조대, 시연.
const $ = (s) => document.querySelector(s);
const state = { stations: {}, day: null, morning: null, map: null, layer: null, checked: {}, gu: "", scores: {}, ops: new Set(), busyDemo: {}, busyOps: null, routeValue: null };
let here = null;   // 내 위치 (📍 버튼을 눌렀을 때만)
// QR·입력에서 온 글자를 화면에 넣을 때는 반드시 거친다 (QR 에 HTML 을 심어 두는 장난 막기)
const esc = (x) => String(x).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(path + " " + r.status);
  return r.json();
}

// ── 탭
document.querySelectorAll("#tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    document.querySelectorAll("#tabs button").forEach((x) => { x.classList.toggle("on", x === b); x.setAttribute("aria-selected", x === b); });
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.id === b.dataset.tab));
    if (b.dataset.tab === "morning" && state.map) setTimeout(() => state.map.invalidateSize(), 50);
    if (b.dataset.tab === "rescue") renderRescue();
    window.scrollTo(0, 0);
  })
);

// ── 아침 목록
let liveTimer = null;
async function loadDay(day) {
  state.day = day;
  clearInterval(liveTimer);
  state.morning = await getJSON(day === "live" ? `data/live.json?t=${Date.now()}` : `data/${state.ops.has(day) ? "ops" : "morning"}/${day}.json`);
  if (day === "live") liveTimer = setInterval(() => state.day === "live" && refreshLive(), 60e3);
  state.morning.bikes.forEach((b) => (b.station_name = String(b.station_name).trim()));
  guOptions();
  renderMorning();
  renderRescue();
  loadChecked();
}

// 실시간: server/live.py 가 1분마다 쓰는 data/live.json (반납하자마자 올라오는 서울 대여이력 API)
async function refreshLive() {
  try { state.morning = await getJSON(`data/live.json?t=${Date.now()}`); } catch { return; }
  state.morning.bikes.forEach((b) => (b.station_name = String(b.station_name).trim()));
  guOptions(); renderMorning();
}
const minsAgo = (iso) => Math.max(0, Math.round((Date.now() - new Date(iso + "+09:00").getTime()) / 60e3));

// 구(區) 고르기 — 정비는 구역 단위로 움직인다. 고른 구의 자전거만 요약·지도·순위·동선·목록에.
const guOf = (b) => (state.stations[b.station] || {}).gu || "기타";
const shown = () => (state.morning ? state.morning.bikes.filter((b) => !state.gu || guOf(b) === state.gu) : []);
function guOptions() {
  const n = {};
  state.morning.bikes.forEach((b) => (n[guOf(b)] = (n[guOf(b)] || 0) + 1));
  if (state.gu && !n[state.gu]) state.gu = "";
  $("#gu").innerHTML = `<option value="">서울 전체 (${state.morning.bikes.length}대)</option>` +
    Object.keys(n).sort((a, b) => a.localeCompare(b, "ko")).map((g) => `<option value="${esc(g)}" ${g === state.gu ? "selected" : ""}>${esc(g)} (${n[g]}대)</option>`).join("");
}
function renderMorning() {
  const bikes = shown();
  const red = bikes.filter((b) => b.level === "빨강").length;
  const known = bikes.filter((b) => typeof b.reported === "boolean");   // 운영 목록은 신고 자료가 없어 모름(null)
  const unrep = known.filter((b) => !b.reported).length;
  if (state.day === "live") {
    const sc = state.morning.score || {};
    $("#morning-summary").innerHTML =
      `<b>지금</b> <b>${bikes.length}</b>대가 서로 다른 사람들이 빌리자마자 반납한 채로 서 있어요 (빨강 ${red}대). ` +
      `<span class="muted">${minsAgo(state.morning.at)}분 전 갱신 · 오늘 켜진 경보 ${state.morning.today_alarms}번</span>` +
      (sc.scored ? `<br>실시간 경보 채점: 경보 뒤 처음 빌린 다른 사람 ${sc.scored}명 중 <b class="confirmed">${sc.next_rider_dud}명(${sc["precision_%"]}%)</b>이 또 바로 반납 (평소 약 2.5%)` : "");
    if (state.gu) $("#morning-summary").insertAdjacentHTML("afterbegin", `<b>${esc(state.gu)}</b> — `);
    renderMap(bikes); renderRetro(bikes); renderLists(); renderStories();
    return;
  }
  $("#morning-summary").innerHTML =
    `<b>${bikes.length}</b>대가 어제까지 서로 다른 사람들이 빌리자마자 반납한 채로 남아 있어요 ` +
    `(빨강 ${red}대).` + (known.length ? ` 이 중 <b>${unrep}</b>대는 아직 아무도 고장 신고를 안 했어요.` : "");
  if (state.gu) $("#morning-summary").insertAdjacentHTML("afterbegin", `<b>${esc(state.gu)}</b> — `);
  renderMap(bikes);
  renderRetro(bikes);
  renderLists();
  renderStories();
}
$("#gu").addEventListener("change", (e) => {
  state.gu = e.target.value;
  renderMorning();
  if (state.map && state.layer) { const b = state.layer.getLayers().map((m) => m.getLatLng()); if (b.length) state.map.fitBounds(L.latLngBounds(b).pad(0.2), { maxZoom: 14 }); }
});

const GU_EN = { 강남구: "gangnam", 강동구: "gangdong", 강북구: "gangbuk", 강서구: "gangseo", 관악구: "gwanak", 광진구: "gwangjin", 구로구: "guro",
  금천구: "geumcheon", 노원구: "nowon", 도봉구: "dobong", 동대문구: "dongdaemun", 동작구: "dongjak", 마포구: "mapo", 서대문구: "seodaemun",
  서초구: "seocho", 성동구: "seongdong", 성북구: "seongbuk", 송파구: "songpa", 양천구: "yangcheon", 영등포구: "yeongdeungpo", 용산구: "yongsan",
  은평구: "eunpyeong", 종로구: "jongno", 중구: "jung", 중랑구: "jungnang" };
// 정비 담당에게 보낼 목록 — 엑셀에서 바로 열리게(UTF-8 BOM). 서버 없이 폰·정적 호스팅에서도 된다.
function morningCSV(bikes) {
  const q = (x) => `"${String(x ?? "").replace(/"/g, '""')}"`;
  const head = ["기준일", "구", "대여소번호", "대여소", "자전거번호", "서로 다른 사람 연속 헛대여(명)", "단계", "마지막 헛대여", "고장 신고", "사람 확인(구조대·현장 조사)"];
  const rows = groupByStation(bikes).flatMap(([, arr]) => arr).map((b) => {
    const c = checkedOf(b.bike);
    return [state.day, guOf(b), b.station, b.station_name, b.bike, b.chain, b.level, b.last_dud, b.reported === true ? "있음" : b.reported === false ? "없음" : "모름",
      c.total ? `고장 ${c.broken}/${c.total}` : ""];
  });
  return "\ufeff" + [head, ...rows].map((r) => r.map(q).join(",")).join("\r\n") + "\r\n";
}
$("#csv-btn").addEventListener("click", () => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([morningCSV(shown())], { type: "text/csv;charset=utf-8" }));
  // 파일 이름은 영문만 — 한글 이름은 일부 브라우저가 'download' 로 바꿔 버린다(구 이름은 표 안에 있다)
  a.download = `morning_${state.day}${state.gu ? "_" + (Object.keys(GU_EN).includes(state.gu) ? GU_EN[state.gu] : "gu") : ""}.csv`;
  document.body.appendChild(a); a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
});

// 뒤돌아 채점 — 지난 기록이라 '이 목록이 나온 뒤 처음 빌린 사람' 이 어땠는지 안다 (운영에서는 다음 날 아침 채점: server/daily_job.py)
function renderRetro(bikes) {
  const known = bikes.filter((b) => typeof b.truth_first_rider_dud === "boolean");
  const box = $("#morning-retro");
  const sc = state.scores[state.day];
  if (!known.length && sc && !state.gu) {   // 운영: 다음 날 아침 매일 작업이 채점해 둔 것
    box.hidden = false;
    box.innerHTML = `<b>이 목록은 맞았을까?</b> 다음 날 아침 채점: 목록 ${sc.listed}대 중 그날 누가 빌린 ${sc.rode}대, 첫 이용자 ` +
      `<b class="confirmed">${sc.first_dud}명(${sc.rode ? Math.round((100 * sc.first_dud) / sc.rode) : 0}%)</b>이 또 바로 반납했어요. 평소엔 약 2.5% 예요.`;
    return;
  }
  if (!known.length) { box.hidden = true; return; }
  const hit = known.filter((b) => b.truth_first_rider_dud).length;
  box.hidden = false;
  box.innerHTML = `<b>이 목록은 맞았을까?</b> (지난 기록이라 채점할 수 있어요) 목록이 나온 뒤 처음 빌린 사람 <b>${known.length}</b>명 중 ` +
    `<b class="confirmed">${hit}명(${Math.round((100 * hit) / known.length)}%)</b>이 또 바로 반납했어요. 평소엔 약 2.5% 예요.` +
    (bikes.length > known.length ? ` <span class="muted">(${bikes.length - known.length}대는 그 뒤 아무도 안 빌림)</span>` : "");
}
function renderLists() {
  if (!state.morning) return;
  const bikes = shown();
  renderRank(bikes);
  renderRoute(bikes);
  $("#bike-list").innerHTML = bikes.slice(0, 80).map(bikeRow).join("");
}

// 정비 동선: 순위 위 10곳을 (내 위치 또는 1위 대여소에서) 도는 순서 — route.js
// 정비 동선 — 근무 시간 안에 '막을 헛걸음' 이 가장 많은 대여소와 순서 (route.js planValue, 되짚기: docs/route_backtest.md)
// 대여소 값 = 목록 자전거마다 그날 낼 헛걸음 평균(연쇄 길이 × 대여소 붐빔, route_value.json) × 도착 뒤 남은 대여 비율(busy.json 시간대별)
function stationValue(s, minute) {
  const rv = state.routeValue;
  if (!rv) return s.arr.length * Math.max(0, (1440 - minute) / 1440);
  const busy = (state.day === "live" || state.ops.has(state.day)) && state.busyOps ? state.busyOps : state.busyDemo;
  const b = busy[s.id];
  const avg = b ? b[0] : 0, h = b ? b.slice(1).map((x) => x + 0.5) : Array(24).fill(1);
  const lvl = avg < rv.cuts[0] ? 0 : avg < rv.cuts[1] ? 1 : 2;
  return s.arr.reduce((t, bike) => t + rv.value[String(Math.min(Math.max(bike.chain, 2), 4))][lvl], 0) * shareAfter(h, minute);
}
function routeStart() {   // 운영(오늘·실시간)이면 지금부터, 지난 날(시연)이면 그날 9시부터
  const today = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
  if (state.day === "live" || state.day === today) { const n = new Date(); return n.getHours() * 60 + n.getMinutes(); }
  return 9 * 60;
}
const hhmm = (m) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(Math.floor(m % 60)).padStart(2, "0")}`;
function renderRoute(bikes) {
  const minutes = +$("#shift").value, t0 = routeStart();
  let groups = groupByStation(bikes).map(([id, arr]) => ({ id, arr, n: arr.length, ...state.stations[id] })).filter((s) => s.lat);
  if (!groups.length) { $("#route-list").innerHTML = ""; if (state.routeLayer) state.routeLayer.remove(); return; }
  // 후보는 값이 큰 40곳까지 (서울 전체를 한 사람이 도는 건 비현실적 — 기사는 구역 단위로 움직인다: 구를 고르면 그 구 안에서)
  groups = groups.sort((a, b) => stationValue(b, t0) - stationValue(a, t0)).slice(0, 40);
  const start = here ? { lat: here.lat, lon: here.lon, name: "내 위치" } : groups[0];
  const stops = planValue(start, groups, stationValue, minutes, t0);
  const sim = simulate(start, stops, stationValue, t0);
  // 비교: 지금까지의 방식(누적 헛걸음 순위대로 가장 짧게) 을 같은 시간만큼 돌았다면
  const rank = groupByStation(bikes).map(([id, arr]) => ({ id, arr, n: arr.length, ...state.stations[id] })).filter((s) => s.lat).slice(0, 10);
  const rankStops = withinShift(start, planRoute(start, rank), minutes);
  const rankValue = simulate(start, rankStops, stationValue, t0).value;
  $("#route-list").innerHTML = stops.map((s, i) =>
    `<li><div><b>${esc(s.name)}</b><br><span class="muted">도착 약 ${hhmm(sim.arr[i])} · 의심 ${s.arr.length}대 · 막을 헛걸음 예상 ${stationValue(s, sim.arr[i]).toFixed(1)}명</span></div>` +
    `<span class="tag ${s.arr.some((b) => b.level === "빨강") ? "빨강" : "노랑"}">${s.arr.length}</span></li>`).join("") +
    `<li class="total"><span>${here ? "내 위치에서 " : ""}${stops.length}곳 · 약 ${Math.round(sim.used)}분 · 막을 헛걸음 예상 <b>${sim.value.toFixed(1)}명</b>` +
    `${sim.value > rankValue + 0.05 ? ` <span class="muted">(순위대로 돌 때보다 ${(sim.value - rankValue).toFixed(1)}명 더)</span>` : ""}</span></li>`;
  if (typeof L === "undefined" || !state.map) return;
  if (state.routeLayer) state.routeLayer.remove();
  state.routeLayer = L.layerGroup().addTo(state.map);
  L.polyline([start, ...stops].map((p) => [p.lat, p.lon]), { color: "#0f766e", weight: 3, opacity: 0.8, dashArray: "6 6" }).addTo(state.routeLayer);
  stops.forEach((s, i) => L.marker([s.lat, s.lon], { icon: L.divIcon({ className: "route-num", html: String(i + 1), iconSize: [20, 20] }) }).addTo(state.routeLayer));
}

// 위치 한 번 받기 (아이폰은 https 에서만) — 구조대·동선·현장 조사가 같이 쓴다
function locate() {
  return new Promise((ok, no) => {
    if (!navigator.geolocation) return no(new Error("no geolocation"));
    navigator.geolocation.getCurrentPosition((p) => { here = { lat: p.coords.latitude, lon: p.coords.longitude }; ok(here); }, no,
      { enableHighAccuracy: true, timeout: 8000 });
  });
}
const noLocation = () => toast("위치를 쓸 수 없어요(아이폰은 https 주소에서만). 목록 순서대로 보여 줄게요.");

// 구조대가 서버에 보낸 확인 결과 (자전거별 {판정: 명}) — 정비 순위에 '사람이 봤음' 으로 붙인다. 서버가 없으면(정적·오프라인) 조용히 건너뜀.
async function loadChecked() {
  try { const r = await fetch("api/rescue"); if (r.ok) { state.checked = await r.json(); renderLists(); } } catch {}
}
function checkedOf(bike) {
  const v = state.checked[bike] || {};
  const total = Object.values(v).reduce((a, b) => a + b, 0);
  return { total, broken: total - (v["멀쩡함"] || 0) };
}
function checkedBadge(bike) {
  const c = checkedOf(bike);
  if (!c.total) return "";
  return c.broken ? ` · <b class="confirmed">사람 확인: 고장 ${c.broken}/${c.total}</b>` : ` · 사람 확인: 멀쩡함 ${c.total}`;
}

// 의심 자전거 하나 = 인스타 게시물 하나: 머리(자전거 번호·대여소·언제), 큰 숫자 카드, 단추(3초 확인·자세히), 설명
const ago = (b) => typeof b.minutes_ago === "number" ? (b.minutes_ago < 60 ? `${b.minutes_ago}분 전` : b.minutes_ago < 1440 ? `${Math.floor(b.minutes_ago / 60)}시간 전` : `${Math.floor(b.minutes_ago / 1440)}일 전`) : `마지막 ${b.last_dud}`;
function bikeRow(b) {
  const gu = (state.stations[b.station] || {}).gu;
  const tail = [
    b.reported === true ? "신고됨" : b.reported === false ? "<b>아직 아무도 신고 안 함</b>" : "",
    b.truth_first_rider_dud === true ? "다음 사람도 반납" : b.truth_first_rider_dud === false ? "다음 사람은 탐" : "",
  ].filter(Boolean).join(" · ");
  return `<li class="post">` +
    `<div class="post-head"><span class="ava" aria-hidden="true"><span>🚲</span></span>` +
    `<div class="who"><b>${esc(b.bike)}</b><span>${esc(b.station_name)}${gu ? " · " + esc(gu) : ""} · ${ago(b)}</span></div>` +
    `<span class="tag ${b.level}">${b.level}</span></div>` +
    `<div class="post-card ${b.level}"><strong>${b.chain}</strong><span>명이 연달아<br>빌리자마자 반납했어요</span></div>` +
    `<div class="post-actions"><button class="go" data-act="check" data-bike="${esc(b.bike)}">🙋 3초 확인</button>` +
    `<button data-act="look" data-bike="${esc(b.bike)}">🔎 자세히</button></div>` +
    `<div class="post-caption"><span class="muted">서로 다른 ${b.chain}명 연속 · 마지막 ${esc(b.last_dud)}${tail ? " · " : ""}</span>${tail}${checkedBadge(b.bike)}</div></li>`;
}
function showTab(t) {
  const btn = document.querySelector(`#tabs button[data-tab="${t}"]`);
  if (btn) btn.click();
}
$("#bike-list").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-act]");
  if (!btn) return;
  const bike = btn.dataset.bike;
  if (btn.dataset.act === "check") { state.focusBike = bike; showTab("rescue"); }
  else { showTab("lookup"); $("#bike-input").value = bike; lookup(bike); }
});

// 스토리 = 구 고르기: 의심 자전거가 많은 구부터, 고른 구는 테두리로
function renderStories() {
  if (!state.morning) return;
  const n = {};
  state.morning.bikes.forEach((b) => (n[guOf(b)] = (n[guOf(b)] || 0) + 1));
  const items = [["", "전체", state.morning.bikes.length], ...Object.entries(n).sort((a, b) => b[1] - a[1]).map(([g, c]) => [g, g, c])];
  $("#stories").innerHTML = items.map(([v, name, c]) =>
    `<button class="story${v === state.gu ? " on" : ""}" data-gu="${esc(v)}" aria-pressed="${v === state.gu}" aria-label="${esc(name)} ${c}대">` +
    `<span class="ring"><span${v ? "" : ' class="all"'}>${v ? c : "🚲"}</span></span><em>${esc(name.replace(/구$/, "") || name)}</em></button>`).join("");
}
$("#stories").addEventListener("click", (e) => {
  const st = e.target.closest(".story");
  if (!st) return;
  $("#gu").value = st.dataset.gu;
  $("#gu").dispatchEvent(new Event("change"));
});

function groupByStation(bikes) {
  const g = {};
  bikes.forEach((b) => (g[b.station] = g[b.station] || []).push(b));
  // 우선순위: 구조대가 고장이라고 확인한 자전거가 있는 곳 먼저, 그다음 연쇄 길이의 합 (그만큼 사람들이 이미 헛걸음했고, 앞으로도 날 가능성이 큼)
  return Object.entries(g).sort((a, b) => sumBroken(b[1]) - sumBroken(a[1]) || sumChain(b[1]) - sumChain(a[1]) || b[1].length - a[1].length);
}
const sumBroken = (arr) => arr.filter((b) => checkedOf(b.bike).broken > 0).length;
const maxChain = (arr) => Math.max(...arr.map((b) => b.chain));
const sumChain = (arr) => arr.reduce((t, b) => t + b.chain, 0);

function renderRank(bikes) {
  $("#station-rank").innerHTML = groupByStation(bikes).slice(0, 10).map(([id, arr]) => {
    const s = state.stations[id];
    const nb = sumBroken(arr);
    return `<li><div><b>${s ? s.name : id}</b><br><span class="muted">${s ? s.gu : ""} · 의심 ${arr.length}대 · 헛걸음 ${sumChain(arr)}명 누적 (최대 ${maxChain(arr)}명 연속)` +
      `${nb ? ` · <b class="confirmed">구조대 확인 고장 ${nb}대</b>` : ""}</span></div>` +
      `<span class="tag ${arr.some((b) => b.level === "빨강") ? "빨강" : "노랑"}">${arr.length}</span></li>`;
  }).join("");
}

// 지도 바탕: 지도 조각(인터넷) + 대여소 전체를 옅은 점으로 — 오프라인이라 조각이 없어도 점들이 서울 모양을 그린다
function baseMap(id, opts = {}) {
  const map = L.map(id, opts).setView([37.55, 126.99], 11);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, crossOrigin: true, attribution: "© OpenStreetMap" }).addTo(map);
  const r = L.canvas({ padding: 0.5 });
  Object.values(state.stations).forEach((s) =>
    L.circleMarker([s.lat, s.lon], { renderer: r, radius: 1.5, stroke: false, fillColor: "#64748b", fillOpacity: 0.35, interactive: false }).addTo(map));
  return map;
}

function renderMap(bikes) {
  if (typeof L === "undefined") { $("#map").textContent = "지도를 불러오지 못했어요(오프라인). 아래 목록을 보세요."; return; }
  if (!state.map) state.map = baseMap("map");
  if (state.layer) state.layer.remove();
  state.layer = L.layerGroup().addTo(state.map);
  groupByStation(bikes).forEach(([id, arr]) => {
    const s = state.stations[id];
    if (!s) return;
    const red = arr.some((b) => b.level === "빨강");
    L.circleMarker([s.lat, s.lon], { radius: 5 + 2 * arr.length, color: red ? "#d9480f" : "#e0a100", weight: 1.5, fillOpacity: 0.5 })
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
      `${state.day === "live" ? "최근" : "어제까지"} <b>서로 다른 ${hit.chain}명</b>이 이 자전거를 빌리자마자 반납했어요 (마지막 ${hit.last_dud}, ${hit.station_name}).<br>` +
      `이런 자전거는 다음 사람도 ${hit.level === "빨강" ? "약 70%" : "약 35~55%"}가 바로 반납했어요. 옆 자전거를 고르세요.` +
      `<div class="choices"><button onclick="rescueSave('${id}','체인·기어')">체인·기어 문제</button><button onclick="rescueSave('${id}','타이어')">타이어</button>` +
      `<button onclick="rescueSave('${id}','안장·핸들')">안장·핸들</button><button class="fine" onclick="rescueSave('${id}','멀쩡함')">멀쩡해 보여요</button></div></div>`;
  } else {
    out.innerHTML = m ? `<div class="result ok"><h3>✓ ${esc(id)}</h3>${state.day === "live" ? "최근" : "어제까지"} 기록에 헛걸음 연쇄가 없어요.</div>`
      : `<div class="result">따릉이 번호(SPB-00000)를 못 찾았어요: <code>${esc(String(raw).slice(0, 60))}</code></div>`;
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

// ── 구조대 (이 기기에 남기고, 서버가 있으면 정비 쪽으로 보냄)
function rescueLog() { try { return JSON.parse(localStorage.getItem("rescue") || "[]"); } catch { return []; } }
window.rescueSave = async (bike, verdict) => {
  const log = rescueLog();
  log.unshift({ bike, verdict, at: new Date().toLocaleString("ko-KR"), day: state.day });
  try { localStorage.setItem("rescue", JSON.stringify(log.slice(0, 200))); } catch {}
  renderRescue();
  // 서버가 있으면 정비 쪽으로 보낸다. 없으면(정적 호스팅·오프라인) 이 기기에만 남는다.
  let sent = "";
  try {
    const r = await fetch("api/rescue", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bike, verdict, day: state.day }) });
    if (r.ok) { const j = await r.json(); sent = ` 지금까지 ${j.count}명이 이 자전거를 확인했어요.`; loadChecked(); }
  } catch {}
  toast(`고마워요! ${bike} 를 "${verdict}" 로 기록했어요.${sent}`);
};
function toast(msg) {
  const t = document.createElement("div");
  t.className = "toast"; t.textContent = msg; t.setAttribute("role", "status");   // 화면 읽기 프로그램이 읽어 줌
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3200);
}
function renderRescue() {
  if (!state.morning) return;
  const done = new Set(rescueLog().filter((x) => x.day === state.day).map((x) => x.bike));
  let todo = state.morning.bikes.filter((b) => !done.has(b.bike));
  const focused = !!state.focusBike;
  if (state.focusBike) {   // 게시물의 '3초 확인' 으로 온 자전거를 맨 앞에
    const f = todo.find((b) => b.bike === state.focusBike);
    if (f) todo = [f, ...todo.filter((b) => b !== f)];
    state.focusBike = null;
  }
  const far = (b) => (here && state.stations[b.station] ? meters(here, state.stations[b.station]) : null);
  if (here && !focused) todo = todo.slice().sort((a, b) => (far(a) ?? 1e12) - (far(b) ?? 1e12));   // 위치를 알면 가까운 순
  const next = todo[0];
  const away = (b) => (far(b) == null ? "" : far(b) < 1000 ? ` · ${Math.round(far(b))}m` : ` · ${(far(b) / 1000).toFixed(1)}km`);
  $("#rescue-card").innerHTML = next
    ? `<div class="result warn"><h3>${next.station_name}의 ${next.bike}${away(next)}</h3>서로 다른 ${next.chain}명이 바로 반납했어요. 가까이 있다면 3초만 봐 주세요.` +
      `<div class="choices"><button onclick="rescueSave('${next.bike}','체인·기어')">체인·기어</button><button onclick="rescueSave('${next.bike}','타이어')">타이어</button>` +
      `<button onclick="rescueSave('${next.bike}','안장·핸들')">안장·핸들</button><button class="fine" onclick="rescueSave('${next.bike}','멀쩡함')">멀쩡해요</button></div></div>`
    : `<div class="result ok">오늘 목록을 다 확인했어요!</div>`;
  if (next && todo.length > 1)
    $("#rescue-card").insertAdjacentHTML("beforeend", `<p class="muted">그다음: ${todo.slice(1, 4).map((b) => `${b.station_name} ${b.bike}${away(b)}`).join(" · ")}</p>`);
  $("#rescue-log").innerHTML = rescueLog().slice(0, 20).map((x) =>
    `<li><div><b>${x.bike}</b><br><span class="muted">${x.at}</span></div><span class="tag ${x.verdict === "멀쩡함" ? "ok" : "빨강"}">${x.verdict}</span></li>`).join("");
}

// ── 시연
let replay = null, timer = null, rmap = null, rlayer = null;
const COLORS = { "경보": "#d9480f", "막을 수 있던 헛걸음": "#2b8a3e", "고장 신고": "#0f766e" };
function flash(e) {
  if (!rmap) return;
  const s = state.stations[e.station] || (e.type === "고장 신고" && lastStation[e.bike] && state.stations[lastStation[e.bike]]);
  if (!s) return;
  const m = L.circleMarker([s.lat, s.lon], { radius: e.type === "경보" ? 9 : 7, color: COLORS[e.type], weight: 2, fillOpacity: 0.6 }).addTo(rlayer);
  let life = 30;   // 3초에 걸쳐 흐려짐
  const fade = setInterval(() => { life -= 1; m.setStyle({ opacity: life / 30, fillOpacity: 0.6 * life / 30 }); if (life <= 0) { clearInterval(fade); m.remove(); } }, 100);
}
const lastStation = {};
async function startReplay() {
  if (!replay) replay = await getJSON("data/replay_2026-06-15.json");
  if (!rmap && typeof L !== "undefined") {
    rmap = baseMap("replay-map", { zoomControl: false });
    rlayer = L.layerGroup().addTo(rmap);
  }
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
      if (e.station) lastStation[e.bike] = e.station;
      if (e.type !== "헛대여") flash(e);
      if (e.type !== "헛대여") {
        const s = state.stations[e.station];
        const text = e.type === "고장 신고" ? `${e.t} 고장 신고 들어옴 — ${e.bike} (${e.kind}) · 우리 경보는 이미 울렸음`
          : e.type === "경보" ? `${e.t} 경보 — ${e.bike} 서로 다른 ${e.chain}명 연속 (${s ? s.name : e.station})`
          : `${e.t} 막을 수 있던 헛걸음 — ${e.bike} (${s ? s.name : e.station})`;
        feed.insertAdjacentHTML("afterbegin", `<li class="${e.type.split(" ")[0]}">${text}</li>`);
      }
    }
    const m = Math.floor((clock % 3600) / 60);
    $("#clock").textContent = (clock >= 86400 ? "다음 날 " : "") + `${String(Math.floor(clock / 3600) % 24).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    $("#c-dud").textContent = c["헛대여"] + c["경보"] + c["막을 수 있던 헛걸음"];
    $("#c-alarm").textContent = c["경보"];
    $("#c-prev").textContent = c["막을 수 있던 헛걸음"];
    $("#c-fault").textContent = c["고장 신고"];
    if (i >= replay.events.length) { clearInterval(timer); timer = null; $("#play").textContent = "▶ 다시"; }
  }, 100);
}
$("#play").addEventListener("click", startReplay);

// 처음 보여 줄 날: 주소에 ?day= 가 있으면 그날, 운영 중이면(최근 3일 안 목록) 가장 새 목록, 아니면 시연 날짜(6/15)
function defaultDay(days) {
  const want = new URLSearchParams(location.search).get("day");
  if (want && days.includes(want)) return want;
  const latest = days[days.length - 1];
  const fresh = latest && Date.now() - new Date(latest + "T00:00:00+09:00").getTime() < 3 * 86400e3;
  return fresh ? latest : days.includes("2026-06-15") ? "2026-06-15" : latest;
}

// ── 시작
(async () => {
  const list = await getJSON("data/stations.json");
  list.forEach((s) => { s.name = s.name.trim(); state.stations[s.id] = s; });   // 원본 이름 앞에 빈칸이 붙은 곳이 많다
  // 시연 목록(data/morning, 월별 파일) + 운영 목록(data/ops, 매일 06:10 — 서버에만 있음)
  const ops = await getJSON("data/ops/index.json").catch(() => []);
  state.ops = new Set(ops);
  const days = [...new Set([...(await getJSON("data/morning/index.json")), ...ops])].sort();
  try { state.scores = await getJSON("data/ops/scores.json"); } catch {}   // 운영 중에만 있음
  state.routeValue = await getJSON("data/route_value.json").catch(() => null);   // 정비 동선 값 표
  // 대여소 시간대별 대여 — 시연 날짜는 그때 자료(busy.json, 6/15 앞 7일), 운영(실시간·매일 목록)은 서버가 지난 7일로 쓴 ops/busy.json
  state.busyDemo = await getJSON("data/busy.json").catch(() => ({}));
  state.busyOps = await getJSON("data/ops/busy.json").catch(() => null);
  let live = null;
  try { live = await getJSON(`data/live.json?t=${Date.now()}`); if (minsAgo(live.at) > 20) live = null; } catch {}
  const pick = live && !new URLSearchParams(location.search).get("day") ? "live" : defaultDay(days);
  $("#day").innerHTML = (live ? `<option value="live" ${pick === "live" ? "selected" : ""}>지금 (실시간)</option>` : "") +
    days.map((d) => `<option ${d === pick ? "selected" : ""}>${d}</option>`).join("");
  $("#day").addEventListener("change", (e) => loadDay(e.target.value));
  await loadDay($("#day").value);
  stationOptions(null);
  flushQueue();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
})();

// ── 현장 조사 (검증용): 보이는 그대로 기록 → 서버, 안 되면 폰에 모아 두고 다음에 보냄
const SURVEY_STATUS = ["멀쩡함", "타이어", "체인·기어", "안장·핸들", "브레이크", "기타 고장"];
function queue() { try { return JSON.parse(localStorage.getItem("survey_queue") || "[]"); } catch { return []; } }
function setQueue(q) { try { localStorage.setItem("survey_queue", JSON.stringify(q)); return true; } catch { return false; } }
async function flushQueue() {
  const q = queue(); const left = [];
  for (const rec of q) {
    try {
      let r = await fetch("api/survey", { method: "POST", body: JSON.stringify(rec) });
      if (r.status === 400 && rec.photo) {   // 사진이 거절돼도 본 기록은 살린다
        const { photo, ...plain } = rec;
        r = await fetch("api/survey", { method: "POST", body: JSON.stringify(plain) });
      }
      if (!r.ok && r.status !== 400) left.push(rec);   // 400 = 잘못된 기록 → 버림, 그 밖(서버 문제) → 다음에 다시
    } catch { left.push(rec); }
  }
  setQueue(left);
  return left.length;
}
function stationOptions(center, filter = "") {
  const list = Object.values(state.stations).filter((s) => !filter || s.name.includes(filter));
  if (center) list.sort((a, b) => dist(a, center) - dist(b, center));
  else list.sort((a, b) => a.name.localeCompare(b.name, "ko"));
  $("#survey-station").innerHTML = list.slice(0, center ? 30 : 3000)
    .map((s) => `<option value="${s.id}">${s.name}${center ? ` · ${Math.round(dist(s, center))}m` : ""}</option>`).join("");
}
const dist = (a, b) => meters(a, b);
$("#station-filter").addEventListener("input", (e) => stationOptions(here, e.target.value.trim()));
$("#near-btn").addEventListener("click", () =>
  locate().then(() => stationOptions(here, $("#station-filter").value.trim()), () => toast("위치를 쓸 수 없어요(아이폰은 https 주소에서만). 이름으로 찾아 주세요.")));
$("#rescue-near").addEventListener("click", () => locate().then(renderRescue, noLocation));
$("#route-here").addEventListener("click", () => locate().then(renderLists, noLocation));
$("#shift").addEventListener("change", () => renderLists());
// 사진(선택): 폰에서 긴 변 1280px JPEG 로 줄여서 보낸다 (원본 몇 MB → 약 150KB). 번호판·얼굴이 안 나오게 — 절차 문서.
let surveyPhoto = null;
async function shrink(file, max = 1280, q = 0.7) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = url; });
    const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", q);
  } finally { URL.revokeObjectURL(url); }
}
function setSurveyPhoto(dataUrl) {
  surveyPhoto = dataUrl;
  $("#survey-thumb").hidden = !dataUrl;
  if (dataUrl) $("#survey-thumb").src = dataUrl; else $("#survey-thumb").removeAttribute("src");
  $("#survey-photo-label").textContent = dataUrl ? `📷 사진 붙음 (${Math.round(dataUrl.length * 0.75 / 1024)}KB) — 다시 누르면 바꿈` : "📷 사진 붙이기 (선택)";
}
$("#survey-photo").addEventListener("change", async (e) => {
  const f = e.target.files && e.target.files[0];
  if (!f) return;
  try { setSurveyPhoto(await shrink(f)); } catch { setSurveyPhoto(null); toast("사진을 읽지 못했어요. 다른 사진으로 해 주세요."); }
  e.target.value = "";
});

$("#survey-choices").innerHTML = SURVEY_STATUS.map((st) => `<button class="${st === "멀쩡함" ? "fine" : "bad"}" data-st="${st}">${st}</button>`).join("");
$("#survey-form").addEventListener("submit", (e) => e.preventDefault());
$("#survey-choices").addEventListener("click", async (e) => {
  const st = e.target.dataset.st; if (!st) return;
  const bike = $("#survey-bike").value.trim();
  if (!/SPB\s*-?\s*\d{3,6}/i.test(bike)) return toast("자전거 번호(SPB-00000)를 먼저 넣어 주세요.");
  const rec = { station: $("#survey-station").value, bike, status: st, note: $("#survey-note").value, lat: here && here.lat, lon: here && here.lon,
                at: new Date().toISOString() };
  if (surveyPhoto) rec.photo = surveyPhoto;
  let dropped = false;
  if (!setQueue([...queue(), rec]) && rec.photo) {   // 폰 저장 공간이 차면 사진만 빼고라도 기록은 남긴다
    delete rec.photo; dropped = true; setQueue([...queue(), rec]);
  }
  const left = await flushQueue();
  const n = (+(localStorage.getItem("survey_n") || 0)) + 1;
  try { localStorage.setItem("survey_n", n); } catch {}
  $("#survey-count").textContent = `오늘 이 기기로 ${n}대 기록${left ? ` (서버에 못 보낸 ${left}건은 폰에 보관 중)` : ""}`;
  $("#survey-bike").value = ""; $("#survey-note").value = ""; setSurveyPhoto(null);
  toast(`${bike.toUpperCase()} → ${st}${rec.photo ? " (사진 포함)" : ""}${dropped ? " — 폰 저장 공간이 모자라 사진은 빼고 보관했어요" : ""}`);
});
