// 정비 동선 — planRoute: 정해진 곳들을 가장 짧게 도는 순서(가까운 곳부터 + 2-opt, 아이폰 앱과 같은 답) · planValue: 근무 시간 안에 가장 많이 막는 곳과 순서.
// 거리는 직선 × 1.3 (실제 길).
// 브라우저에서는 전역 함수, node 검사에서는 require.
function meters(a, b) {
  const R = 6371000, toR = Math.PI / 180, dLat = (b.lat - a.lat) * toR, dLon = (b.lon - a.lon) * toR;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * toR) * Math.cos(b.lat * toR) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}
function pathLength(start, stops) {
  let t = 0, cur = start;
  for (const s of stops) { t += meters(cur, s); cur = s; }
  return t;
}
// start: {lat, lon}, stops: [{lat, lon, ...}] → 같은 점들을 도는 순서 (돌아오지 않는 한 방향 길)
function planRoute(start, stops) {
  const left = stops.slice(), order = [];
  let cur = start;
  while (left.length) {
    let k = 0;
    for (let i = 1; i < left.length; i++) if (meters(cur, left[i]) < meters(cur, left[k])) k = i;
    cur = left.splice(k, 1)[0];
    order.push(cur);
  }
  // 2-opt: 구간 [i..j] 를 뒤집어 짧아지면 바꾼다 (점이 10~20개라 충분히 빠름)
  const pts = [start, ...order];
  for (let improved = true, guard = 0; improved && guard < 50; guard++) {
    improved = false;
    for (let i = 1; i < pts.length - 1; i++) {
      for (let j = i + 1; j < pts.length; j++) {
        const a = pts[i - 1], b = pts[i], c = pts[j], d = pts[j + 1];
        const before = meters(a, b) + (d ? meters(c, d) : 0), after = meters(a, c) + (d ? meters(b, d) : 0);
        if (after < before - 1e-6) { pts.splice(i, j - i + 1, ...pts.slice(i, j + 1).reverse()); improved = true; }
      }
    }
  }
  return pts.slice(1);
}

// ── 막는 동선: 근무 시간 안에 '막을 헛걸음' 이 가장 많은 대여소를 고르고 도는 순서 (engine/route.py 와 같은 풀이)
//    오리엔티어링 문제 — 욕심 삽입(더 얻는 값 ÷ 더 드는 시간이 큰 곳을 가장 좋은 자리에) + 구간 뒤집기(2-opt)
const SHIFT = { kmh: 18, detour: 1.3, stopMin: 6, bikeMin: 4 };   // 정비 차 도심 평균·직선→실제 길·대여소 한 곳·자전거 한 대
const travelMin = (a, b) => meters(a, b) * SHIFT.detour / 1000 / SHIFT.kmh * 60;
// start 에서 t0(분, 0시부터)에 출발해 route 를 돌 때 → { used: 쓴 분, value: 막을 헛걸음 합, arr: 도착 시각들 }
function simulate(start, route, valueAt, t0 = 0) {
  let t = 0, value = 0, cur = start;
  const arr = [];
  for (const s of route) {
    t += travelMin(cur, s);
    arr.push(t0 + t);
    value += valueAt(s, t0 + t);
    t += SHIFT.stopMin + SHIFT.bikeMin * (s.n || 1);
    cur = s;
  }
  return { used: t, value, arr };
}
function twoOptValue(start, route, valueAt, minutes, t0) {
  let best = simulate(start, route, valueAt, t0);
  for (let improved = true, guard = 0; improved && guard < 30; guard++) {
    improved = false;
    for (let i = 0; i < route.length - 1; i++) {
      for (let j = i + 1; j < route.length; j++) {
        const cand = [...route.slice(0, i), ...route.slice(i, j + 1).reverse(), ...route.slice(j + 1)];
        const r = simulate(start, cand, valueAt, t0);
        if (r.used <= minutes && (r.value > best.value + 1e-9 || (Math.abs(r.value - best.value) <= 1e-9 && r.used < best.used - 1e-6))) {
          route = cand; best = r; improved = true;
        }
      }
    }
  }
  return route;
}
// 욕심 삽입: mode "ratio" = 더 얻는 값 ÷ 더 드는 시간, "value" = 더 얻는 값. seed 에서 시작해 못 넣을 때까지.
function greedyFill(start, seed, pool, valueAt, minutes, t0, mode) {
  let route = seed.slice();
  const left = pool.filter((s) => !route.includes(s));
  while (left.length) {
    const base = simulate(start, route, valueAt, t0);
    let best = null;
    for (const s of left) {
      for (let pos = 0; pos <= route.length; pos++) {
        const cand = [...route.slice(0, pos), s, ...route.slice(pos)];
        const r = simulate(start, cand, valueAt, t0);
        if (r.used > minutes || r.value <= base.value + 1e-9) continue;
        const score = mode === "ratio" ? (r.value - base.value) / Math.max(r.used - base.used, 1e-6) : r.value - base.value;
        if (!best || score > best.score) best = { score, cand, s };
      }
    }
    if (!best) break;
    route = twoOptValue(start, best.cand, valueAt, minutes, t0);
    left.splice(left.indexOf(best.s), 1);
  }
  return route;
}
// 여러 방법으로 만들어 보고 가장 많이 막는 것: 값÷시간 욕심, 값 욕심, 값 큰 순서대로 돈 뒤 채우기
function planValue(start, stations, valueAt, minutes, t0 = 0) {
  const byValue = stations.slice().sort((a, b) => valueAt(b, t0) - valueAt(a, t0));
  const seeded = twoOptValue(start, withinShift(start, byValue, minutes), valueAt, minutes, t0);
  const cands = [greedyFill(start, [], stations, valueAt, minutes, t0, "ratio"), greedyFill(start, [], stations, valueAt, minutes, t0, "value"),
    greedyFill(start, seeded, stations, valueAt, minutes, t0, "ratio")];
  return cands.reduce((best, r) => (simulate(start, r, valueAt, t0).value > simulate(start, best, valueAt, t0).value + 1e-9 ? r : best));
}
// 정해진 순서를 근무 시간이 끝날 때까지만 (비교용: 순위대로 돌기)
function withinShift(start, order, minutes) {
  const out = [];
  let t = 0, cur = start;
  for (const s of order) {
    const end = t + travelMin(cur, s) + SHIFT.stopMin + SHIFT.bikeMin * (s.n || 1);
    if (end > minutes) break;
    out.push(s); t = end; cur = s;
  }
  return out;
}
// 대여소의 지난 시간대별 대여(24칸) 중 minute(0시부터 분) 뒤에 남은 몫
function shareAfter(h, minute) {
  const hr = Math.floor(minute / 60);
  if (hr >= 24) return 0;
  const total = h.reduce((a, b) => a + b, 0);
  if (!total) return Math.max(0, (1440 - minute) / 1440);
  let rest = h[hr] * (1 - (minute % 60) / 60);
  for (let i = hr + 1; i < 24; i++) rest += h[i];
  return rest / total;
}
if (typeof module !== "undefined") module.exports = { meters, pathLength, planRoute, SHIFT, travelMin, simulate, planValue, withinShift, shareAfter };
