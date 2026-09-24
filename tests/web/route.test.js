// 정비 동선 단위 검사: node tests/web/route.test.js
const assert = require("assert");
const { meters, pathLength, planRoute } = require("../../web/route.js");
assert(Math.abs(meters({ lat: 37.5, lon: 127 }, { lat: 37.51, lon: 127 }) - 1112) < 5, "위도 0.01° ≈ 1.11km");
// 한 줄로 늘어선 점을 뒤섞어 줘도 끝에서 끝으로 한 번에 간다
const line = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => ({ id: i, lat: 37.5, lon: 127 + 0.01 * i }));
const shuffled = [5, 1, 7, 3, 0, 6, 2, 4].map((i) => line[i]);
const r = planRoute({ lat: 37.5, lon: 126.99 }, shuffled);
assert.deepStrictEqual(r.map((p) => p.id), [0, 1, 2, 3, 4, 5, 6, 7]);
// 가까운 곳부터만 고르면 생기는 되돌아가기를 2-opt 가 줄인다 (무작위 30점 × 20번: 항상 탐욕법 이하)
let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
for (let t = 0; t < 20; t++) {
  const pts = Array.from({ length: 30 }, (_, i) => ({ id: i, lat: 37.45 + 0.15 * rnd(), lon: 126.85 + 0.3 * rnd() }));
  const start = { lat: 37.55, lon: 127 };
  const got = planRoute(start, pts);
  assert.strictEqual(new Set(got.map((p) => p.id)).size, 30, "모든 점을 한 번씩");
  const greedy = []; let cur = start; const left = pts.slice();
  while (left.length) { left.sort((a, b) => meters(cur, a) - meters(cur, b)); cur = left.shift(); greedy.push(cur); }
  assert(pathLength(start, got) <= pathLength(start, greedy) + 1e-6);
}
assert.deepStrictEqual(planRoute({ lat: 0, lon: 0 }, []), []);
console.log("동선 검사 합격");
