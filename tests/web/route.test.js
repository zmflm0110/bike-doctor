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

// ── 막는 동선
const { planValue, simulate, withinShift, shareAfter, SHIFT } = require("../../web/route.js");
assert(Math.abs(shareAfter(Array(24).fill(1), 12 * 60) - 0.5) < 1e-9, "하루 고른 대여면 정오 뒤 남은 몫 절반");
assert.strictEqual(shareAfter([0, ...Array(23).fill(0)], 0), 1, "기록 없으면 남은 시간 비율");
// 가까운 한산한 곳 셋 vs 조금 먼 붐비는 곳 하나 — 시간이 빠듯하면 붐비는 곳을 먼저
const home = { lat: 37.5, lon: 127 };
const quiet = [1, 2, 3].map((i) => ({ id: "q" + i, lat: 37.5 + 0.002 * i, lon: 127, n: 1, v: 0.3 }));
const busy = { id: "b", lat: 37.5, lon: 127.03, n: 1, v: 3 };
const val = (s) => s.v;
const plan40 = planValue(home, [...quiet, busy], val, 40);
assert(plan40.some((s) => s.id === "b"), "40분이면 붐비는 곳을 넣는다");
assert(simulate(home, plan40, val).used <= 40, "근무 시간을 넘지 않는다");
const rankOrder = withinShift(home, [...quiet, busy], 40);
assert(simulate(home, plan40, val).value > simulate(home, rankOrder, val).value, "순서대로 돌기보다 더 막는다");
// 무작위: 언제나 시간 안, 순서대로 돌기 이상
seed = 11;
for (let t = 0; t < 30; t++) {
  const pts = Array.from({ length: 15 }, (_, i) => ({ id: i, lat: 37.45 + 0.1 * rnd(), lon: 126.9 + 0.2 * rnd(), n: 1 + Math.floor(3 * rnd()), v: rnd() * 2 }));
  const minutes = 60 + 120 * rnd();
  const p = planValue(home, pts, val, minutes);
  const r = simulate(home, p, val);
  assert(r.used <= minutes + 1e-9, "시간 안");
  assert.strictEqual(new Set(p.map((x) => x.id)).size, p.length, "한 곳은 한 번만");
  const byValue = withinShift(home, pts.slice().sort((a, b) => b.v - a.v), minutes);
  assert(r.value >= simulate(home, byValue, val).value - 1e-9, "값 큰 순서대로 돌기 이상");
}
console.log("막는 동선 검사 합격");
