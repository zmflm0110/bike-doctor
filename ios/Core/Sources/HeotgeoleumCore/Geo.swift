import Foundation

public struct GeoPoint: Hashable, Sendable {
    public let lat: Double
    public let lon: Double
    public init(lat: Double, lon: Double) { self.lat = lat; self.lon = lon }
}

public enum Geo {
    /// 두 점 사이 직선거리(m) — 하버사인. web/route.js 의 meters 와 같은 식.
    public static func meters(_ a: GeoPoint, _ b: GeoPoint) -> Double {
        let R = 6_371_000.0, toR = Double.pi / 180
        let dLat = (b.lat - a.lat) * toR, dLon = (b.lon - a.lon) * toR
        let x = pow(sin(dLat / 2), 2) + cos(a.lat * toR) * cos(b.lat * toR) * pow(sin(dLon / 2), 2)
        return 2 * R * asin(sqrt(x))
    }

    public static func pathLength(from start: GeoPoint, _ stops: [GeoPoint]) -> Double {
        var t = 0.0, cur = start
        for s in stops { t += meters(cur, s); cur = s }
        return t
    }

    /// 정비 동선: 가까운 곳부터 고른 뒤 2-opt 로 꼬인 구간 풀기 (돌아오지 않는 한 방향 길). web/route.js planRoute 와 같은 순서를 낸다.
    public static func planRoute<T>(from start: GeoPoint, _ stops: [T], point: (T) -> GeoPoint) -> [T] {
        var left = stops, order: [T] = []
        var cur = start
        while !left.isEmpty {
            var k = 0
            for i in 1..<left.count where meters(cur, point(left[i])) < meters(cur, point(left[k])) { k = i }
            let next = left.remove(at: k)
            order.append(next)
            cur = point(next)
        }
        var pts: [GeoPoint?] = [start] + order.map { Optional(point($0)) }
        var items: [T?] = [nil] + order.map { Optional($0) }
        var improved = true, guardCount = 0
        while improved && guardCount < 50 {
            improved = false
            guardCount += 1
            var i = 1
            while i < pts.count - 1 {
                var j = i + 1
                while j < pts.count {
                    let a = pts[i - 1]!, b = pts[i]!, c = pts[j]!
                    let d: GeoPoint? = j + 1 < pts.count ? pts[j + 1] : nil
                    let before = meters(a, b) + (d.map { meters(c, $0) } ?? 0)
                    let after = meters(a, c) + (d.map { meters(b, $0) } ?? 0)
                    if after < before - 1e-6 {
                        pts[i...j].reverse()
                        items[i...j].reverse()
                        improved = true
                    }
                    j += 1
                }
                i += 1
            }
        }
        return items.dropFirst().map { $0! }
    }
}
