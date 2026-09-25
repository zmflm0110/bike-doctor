"""정비 동선 — 근무 시간 안에 '막을 헛걸음' 이 가장 많은 대여소를 고르고, 도는 순서를 정한다.

가장 짧은 길이 아니라 **가장 많이 막는 길**: 붐비는 대여소의 고장 자전거는 곧 또 누가 빌려 헛걸음이 나고,
한산한 곳은 늦게 가도 된다. 시간 안에 점수를 최대로 모으는 경로 = 오리엔티어링 문제.
풀이: 욕심 삽입(더 얻는 헛걸음 ÷ 더 드는 시간이 가장 큰 곳을 가장 좋은 자리에) + 2-opt 로 꼬인 곳 풀기.

값(막을 헛걸음 기대값)은 analysis/route_backtest.py 가 1·3월 기록으로 맞춘 표 VALUE 를 쓴다:
  자전거 한 대 = 그날 남은 헛걸음(연쇄 길이·대여소 붐빔 단계별 평균) × 그 대여소 하루 대여 중 도착 뒤 비율.
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Shift:
    minutes: float = 180.0    # 근무 시간
    kmh: float = 18.0         # 정비 차 도심 평균 속도(신호·주차 포함)
    detour: float = 1.3       # 직선 → 실제 길
    stop_min: float = 6.0     # 대여소 한 곳 (차 대기·찾기)
    bike_min: float = 4.0     # 자전거 한 대 (점검·수거)


def meters(a, b):
    R, r = 6371000.0, math.pi / 180
    dlat, dlon = (b["lat"] - a["lat"]) * r, (b["lon"] - a["lon"]) * r
    x = math.sin(dlat / 2) ** 2 + math.cos(a["lat"] * r) * math.cos(b["lat"] * r) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(x))


def travel_min(a, b, sh=Shift()):
    return meters(a, b) * sh.detour / 1000 / sh.kmh * 60


def simulate(start, route, value_at, sh=Shift(), t0=0.0):
    """start 에서 t0(분)에 출발해 route 를 돌 때: (쓴 분, 막을 헛걸음 합, 도착 시각들). value_at(station, 도착 분) → 기대값."""
    t, total, cur, arr = 0.0, 0.0, start, []
    for s in route:
        t += travel_min(cur, s, sh)
        arr.append(t0 + t)
        total += value_at(s, t0 + t)
        t += sh.stop_min + sh.bike_min * s.get("n", 1)
        cur = s
    return t, total, arr


def plan(start, stations, value_at, sh=Shift(), t0=0.0):
    """근무 시간 안에 막을 헛걸음 기대값이 가장 큰 경로 (욕심 삽입 + 2-opt)."""
    route, left = [], list(stations)
    _, best_v, _ = simulate(start, route, value_at, sh, t0)
    while left:
        best = None
        base_t, base_v, _ = simulate(start, route, value_at, sh, t0)
        for s in left:
            for pos in range(len(route) + 1):
                cand = route[:pos] + [s] + route[pos:]
                t, v, _ = simulate(start, cand, value_at, sh, t0)
                if t > sh.minutes or v <= base_v + 1e-9:
                    continue
                score = (v - base_v) / max(t - base_t, 1e-6)
                if best is None or score > best[0]:
                    best = (score, cand, s)
        if best is None:
            break
        route = best[1]
        left.remove(best[2])
        route = two_opt(start, route, value_at, sh, t0)
    return route


def two_opt(start, route, value_at, sh=Shift(), t0=0.0):
    """구간을 뒤집어 막을 값이 늘거나(같으면 시간이 줄면) 바꾼다."""
    t_best, v_best, _ = simulate(start, route, value_at, sh, t0)
    improved = True
    while improved:
        improved = False
        for i in range(len(route) - 1):
            for j in range(i + 1, len(route)):
                cand = route[:i] + route[i:j + 1][::-1] + route[j + 1:]
                t, v, _ = simulate(start, cand, value_at, sh, t0)
                if t <= sh.minutes and (v > v_best + 1e-9 or (abs(v - v_best) <= 1e-9 and t < t_best - 1e-6)):
                    route, t_best, v_best, improved = cand, t, v, True
    return route


def shortest_order(start, stations, sh=Shift()):
    """(비교용) 지금 앱의 방식 — 가까운 곳부터 고른 뒤 2-opt 로 길이만 줄이기."""
    left, order, cur = list(stations), [], start
    while left:
        k = min(range(len(left)), key=lambda i: meters(cur, left[i]))
        cur = left.pop(k)
        order.append(cur)
    pts = [start] + order
    improved = True
    while improved:
        improved = False
        for i in range(1, len(pts) - 1):
            for j in range(i + 1, len(pts)):
                a, b, c = pts[i - 1], pts[i], pts[j]
                d = pts[j + 1] if j + 1 < len(pts) else None
                before = meters(a, b) + (meters(c, d) if d else 0)
                after = meters(a, c) + (meters(b, d) if d else 0)
                if after < before - 1e-6:
                    pts[i:j + 1] = pts[i:j + 1][::-1]
                    improved = True
    return pts[1:]


def within(start, route, sh=Shift(), t0=0.0):
    """정해진 순서를 근무 시간이 끝날 때까지만 (앞에서부터)."""
    out, t, cur = [], 0.0, start
    for s in route:
        t_arr = t + travel_min(cur, s, sh)
        t_end = t_arr + sh.stop_min + sh.bike_min * s.get("n", 1)
        if t_end > sh.minutes:
            break
        out.append(s)
        t, cur = t_end, s
    return out
