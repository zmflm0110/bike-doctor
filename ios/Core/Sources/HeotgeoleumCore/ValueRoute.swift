import Foundation

/// 막는 동선 — 근무 시간 안에 '막을 헛걸음' 이 가장 많은 대여소와 순서 (web/route.js planValue, engine/route.py plan 과 같은 풀이).
/// 오리엔티어링 문제: 욕심 삽입(값÷시간·값) + 2-opt, 값 큰 순서대로 돈 뒤 채우기 — 셋 중 가장 많이 막는 것.
public struct Shift: Sendable {
    public var minutes: Double
    public var kmh = 18.0          // 정비 차 도심 평균
    public var detour = 1.3        // 직선 → 실제 길
    public var stopMin = 6.0       // 대여소 한 곳
    public var bikeMin = 4.0       // 자전거 한 대
    public init(minutes: Double) { self.minutes = minutes }
}

/// 값 표 (web/data/route_value.json): 목록 자전거 한 대가 그날 낼 헛걸음 평균 — 연쇄 2·3·4+ × 대여소 붐빔 3단계
public struct RouteValue: Codable, Sendable {
    public let cuts: [Double]
    public let value: [String: [Double]]
}

/// 대여소 붐빔 (web/data/busy.json): 번호 → [하루 평균, 0시…23시 대여 수]
public typealias Busy = [String: [Double]]

public enum ValueRoute {
    public struct Stop: Sendable {
        public let station: Station
        public let group: StationGroup
        public init(station: Station, group: StationGroup) { self.station = station; self.group = group }
    }

    static func travelMin(_ a: GeoPoint, _ b: GeoPoint, _ sh: Shift) -> Double { Geo.meters(a, b) * sh.detour / 1000 / sh.kmh * 60 }

    /// start 에서 t0(분)에 출발해 route 를 돌 때 (쓴 분, 막을 헛걸음 합, 도착 시각들)
    public static func simulate(from start: GeoPoint, _ route: [Stop], value: (Stop, Double) -> Double, shift sh: Shift, t0: Double) -> (used: Double, value: Double, arrivals: [Double]) {
        var t = 0.0, total = 0.0, cur = start, arr: [Double] = []
        for s in route {
            t += travelMin(cur, s.station.point, sh)
            arr.append(t0 + t)
            total += value(s, t0 + t)
            t += sh.stopMin + sh.bikeMin * Double(s.group.bikes.count)
            cur = s.station.point
        }
        return (t, total, arr)
    }

    static func twoOpt(from start: GeoPoint, _ route: [Stop], value: (Stop, Double) -> Double, shift sh: Shift, t0: Double) -> [Stop] {
        var route = route
        var best = simulate(from: start, route, value: value, shift: sh, t0: t0)
        var improved = true, guardCount = 0
        while improved && guardCount < 30 {
            improved = false; guardCount += 1
            for i in 0..<max(0, route.count - 1) {
                for j in (i + 1)..<route.count {
                    let cand = Array(route[..<i]) + route[i...j].reversed() + Array(route[(j + 1)...])
                    let r = simulate(from: start, cand, value: value, shift: sh, t0: t0)
                    if r.used <= sh.minutes && (r.value > best.value + 1e-9 || (abs(r.value - best.value) <= 1e-9 && r.used < best.used - 1e-6)) {
                        route = cand; best = r; improved = true
                    }
                }
            }
        }
        return route
    }

    static func greedyFill(from start: GeoPoint, seed: [Stop], pool: [Stop], value: (Stop, Double) -> Double, shift sh: Shift, t0: Double, byRatio: Bool) -> [Stop] {
        var route = seed
        var left = pool.filter { p in !route.contains { $0.group.id == p.group.id } }
        while !left.isEmpty {
            let base = simulate(from: start, route, value: value, shift: sh, t0: t0)
            var best: (score: Double, cand: [Stop], idx: Int)?
            for (k, s) in left.enumerated() {
                for pos in 0...route.count {
                    var cand = route; cand.insert(s, at: pos)
                    let r = simulate(from: start, cand, value: value, shift: sh, t0: t0)
                    if r.used > sh.minutes || r.value <= base.value + 1e-9 { continue }
                    let score = byRatio ? (r.value - base.value) / max(r.used - base.used, 1e-6) : r.value - base.value
                    if best == nil || score > best!.score { best = (score, cand, k) }
                }
            }
            guard let b = best else { break }
            route = twoOpt(from: start, b.cand, value: value, shift: sh, t0: t0)
            left.remove(at: b.idx)
        }
        return route
    }

    /// 정해진 순서를 근무 시간이 끝날 때까지만
    public static func within(from start: GeoPoint, _ order: [Stop], shift sh: Shift) -> [Stop] {
        var out: [Stop] = [], t = 0.0, cur = start
        for s in order {
            let end = t + travelMin(cur, s.station.point, sh) + sh.stopMin + sh.bikeMin * Double(s.group.bikes.count)
            if end > sh.minutes { break }
            out.append(s); t = end; cur = s.station.point
        }
        return out
    }

    public static func plan(from start: GeoPoint, _ stops: [Stop], value: (Stop, Double) -> Double, shift sh: Shift, t0: Double) -> [Stop] {
        let byValue = stops.sorted { value($0, t0) > value($1, t0) }
        let seeded = twoOpt(from: start, within(from: start, byValue, shift: sh), value: value, shift: sh, t0: t0)
        let cands = [greedyFill(from: start, seed: [], pool: stops, value: value, shift: sh, t0: t0, byRatio: true),
                     greedyFill(from: start, seed: [], pool: stops, value: value, shift: sh, t0: t0, byRatio: false),
                     greedyFill(from: start, seed: seeded, pool: stops, value: value, shift: sh, t0: t0, byRatio: true)]
        var best = cands[0]
        for r in cands.dropFirst() where simulate(from: start, r, value: value, shift: sh, t0: t0).value > simulate(from: start, best, value: value, shift: sh, t0: t0).value + 1e-9 { best = r }
        return best
    }

    /// 대여소의 시간대별 대여(24칸) 중 minute(0시부터 분) 뒤에 남은 몫
    public static func shareAfter(_ h: [Double], _ minute: Double) -> Double {
        let hr = Int(minute / 60)
        if hr >= 24 { return 0 }
        let total = h.reduce(0, +)
        if total == 0 { return max(0, (1440 - minute) / 1440) }
        var rest = h[hr] * (1 - minute.truncatingRemainder(dividingBy: 60) / 60)
        for i in (hr + 1)..<24 { rest += h[i] }
        return rest / total
    }

    /// 대여소 값 = 목록 자전거마다 (연쇄 × 붐빔 단계 평균) × 도착 뒤 남은 대여 비율
    public static func stationValue(_ g: StationGroup, busy: Busy, table: RouteValue?, minute: Double) -> Double {
        guard let table else { return Double(g.bikes.count) * max(0, (1440 - minute) / 1440) }
        let b = busy[g.id]
        let avg = b?.first ?? 0
        let h = b.map { Array($0.dropFirst()).map { $0 + 0.5 } } ?? Array(repeating: 1, count: 24)
        let lvl = avg < table.cuts[0] ? 0 : avg < table.cuts[1] ? 1 : 2
        let per = g.bikes.reduce(0.0) { t, bike in t + (table.value[String(min(max(bike.chain, 2), 4))]?[lvl] ?? 0) }
        return per * shareAfter(h, minute)
    }

    public struct Planned: Sendable {
        public let stops: [Stop]
        public let arrivals: [Double]
        public let values: [Double]
        public let used: Double
        public let total: Double
        public let rankTotal: Double
    }

    /// 웹앱 renderRoute 와 같은 규칙: 후보는 값 큰 40곳(같은 값이면 원래 순서 — 자바스크립트 정렬처럼 안정),
    /// 출발은 내 위치 또는 가장 값 큰 대여소. 비교용으로 순위 위 10곳을 가장 짧게 같은 시간만큼 돈 값도.
    public static func planGroups(_ groups: [StationGroup], stations: [String: Station], busy: Busy, table: RouteValue?,
                                  here: GeoPoint?, minutes: Double, t0: Double) -> Planned? {
        let value: (Stop, Double) -> Double = { s, m in stationValue(s.group, busy: busy, table: table, minute: m) }
        let all = groups.compactMap { g in stations[g.id].map { Stop(station: $0, group: g) } }
        let cands = Array(all.enumerated().sorted { a, b in
            let (va, vb) = (value(a.element, t0), value(b.element, t0))
            return va != vb ? va > vb : a.offset < b.offset
        }.map(\.element).prefix(40))
        guard let first = cands.first else { return nil }
        let start = here ?? first.station.point
        let sh = Shift(minutes: minutes)
        let stops = plan(from: start, cands, value: value, shift: sh, t0: t0)
        let sim = simulate(from: start, stops, value: value, shift: sh, t0: t0)
        let rankOrder = Geo.planRoute(from: start, Array(all.prefix(10)), point: { (s: Stop) in s.station.point })
        let rankTotal = simulate(from: start, within(from: start, rankOrder, shift: sh), value: value, shift: sh, t0: t0).value
        return Planned(stops: stops, arrivals: sim.arrivals, values: zip(stops, sim.arrivals).map { value($0, $1) },
                       used: sim.used, total: sim.value, rankTotal: rankTotal)
    }
}
