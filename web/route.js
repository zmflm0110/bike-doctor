// 정비 동선 — 들를 대여소들을 도는 순서 (가까운 곳부터 고른 뒤 2-opt 로 꼬인 곳 풀기). 직선거리라 실제 길은 1.2~1.4배쯤.
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
if (typeof module !== "undefined") module.exports = { meters, pathLength, planRoute };
