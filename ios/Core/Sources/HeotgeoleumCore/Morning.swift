import Foundation

/// 사람이 본 확인 (서버 GET /api/rescue: 자전거별 {판정: 명}, 구조대 + 현장 조사)
public typealias Checked = [String: [String: Int]]

public struct CheckSummary: Hashable, Sendable {
    public let total: Int
    public let broken: Int
}

public func checkSummary(_ checked: Checked, bike: String) -> CheckSummary {
    let v = checked[bike] ?? [:]
    let total = v.values.reduce(0, +)
    return CheckSummary(total: total, broken: total - (v["멀쩡함"] ?? 0))
}

/// 정비 순위의 한 줄 — 한 대여소에 모인 의심 자전거
public struct StationGroup: Identifiable, Hashable, Sendable {
    public let id: String              // 대여소 번호
    public let bikes: [SuspectBike]
    public var sumChain: Int { bikes.reduce(0) { $0 + $1.chain } }
    public var maxChain: Int { bikes.map(\.chain).max() ?? 0 }
    public var hasRed: Bool { bikes.contains(where: \.isRed) }
    public func brokenCount(_ checked: Checked) -> Int { bikes.filter { checkSummary(checked, bike: $0.bike).broken > 0 }.count }
}

public enum Morning {
    /// 대여소별로 묶고 순위: 사람이 고장 확인한 자전거가 있는 곳 → 누적 헛걸음(연쇄 합) → 대수.
    /// 같은 점수끼리의 순서도 웹앱과 같게: 자바스크립트 객체는 '정수처럼 생긴 키'(앞자리 0 없는 번호)를 작은 수부터 먼저,
    /// 나머지는 처음 나온 순서로 둔다 — 그 순서를 그대로 따른다(안정 정렬).
    public static func groupByStation(_ bikes: [SuspectBike], checked: Checked = [:]) -> [StationGroup] {
        var order: [String] = [], g: [String: [SuspectBike]] = [:]
        for b in bikes {
            if g[b.station] == nil { order.append(b.station) }
            g[b.station, default: []].append(b)
        }
        let isIndex: (String) -> Bool = { k in
            guard let n = UInt32(k), n < UInt32.max else { return false }
            return String(n) == k
        }
        let ints = order.filter(isIndex).sorted { UInt32($0)! < UInt32($1)! }
        let keys = ints + order.filter { !isIndex($0) }
        let groups = keys.map { StationGroup(id: $0, bikes: g[$0]!) }
        return groups.enumerated().sorted { x, y in
            let (a, b) = (x.element, y.element)
            let (ba, bb) = (a.brokenCount(checked), b.brokenCount(checked))
            if ba != bb { return ba > bb }
            if a.sumChain != b.sumChain { return a.sumChain > b.sumChain }
            if a.bikes.count != b.bikes.count { return a.bikes.count > b.bikes.count }
            return x.offset < y.offset
        }.map(\.element)
    }

    /// 뒤돌아 채점 (시연 날짜): 목록이 나온 뒤 처음 빌린 사람 중 또 바로 반납한 수
    public static func retro(_ bikes: [SuspectBike]) -> (known: Int, hit: Int, neverRidden: Int) {
        let known = bikes.compactMap(\.truthFirstRiderDud)
        return (known.count, known.filter { $0 }.count, bikes.count - known.count)
    }

    /// 정비 동선: 위치를 모르면 순위 위 10곳을 1위부터, 알면 내 근처 10곳을 내 위치부터.
    public static func route(_ groups: [StationGroup], stations: [String: Station], from here: GeoPoint?, count: Int = 10)
        -> (stops: [Station], meters: Double) {
        var cands = groups.compactMap { stations[$0.id] }
        if let here { cands.sort { Geo.meters(here, $0.point) < Geo.meters(here, $1.point) } }
        let top = Array(cands.prefix(count))
        guard let first = top.first else { return ([], 0) }
        if let here {
            let stops = Geo.planRoute(from: here, top, point: \.point)
            return (stops, Geo.pathLength(from: here, stops.map(\.point)))
        }
        let stops = Geo.planRoute(from: first.point, Array(top.dropFirst()), point: \.point)
        return ([first] + stops, Geo.pathLength(from: first.point, stops.map(\.point)))
    }

    /// 정비 담당용 CSV (엑셀에서 바로 열리게 UTF-8 BOM) — 웹앱과 같은 열
    public static func csv(day: String, bikes: [SuspectBike], stations: [String: Station], checked: Checked = [:]) -> String {
        func q(_ x: String) -> String { "\"" + x.replacingOccurrences(of: "\"", with: "\"\"") + "\"" }
        let head = ["기준일", "구", "대여소번호", "대여소", "자전거번호", "서로 다른 사람 연속 헛대여(명)", "단계", "마지막 헛대여", "고장 신고", "사람 확인(구조대·현장 조사)"]
        let rows = groupByStation(bikes, checked: checked).flatMap(\.bikes).map { b -> [String] in
            let c = checkSummary(checked, bike: b.bike)
            return [day, stations[b.station]?.gu ?? "기타", b.station, b.stationName, b.bike, String(b.chain), b.level, b.lastDud,
                    b.reported ? "있음" : "없음", c.total > 0 ? "고장 \(c.broken)/\(c.total)" : ""]
        }
        return "\u{FEFF}" + ([head] + rows).map { $0.map(q).joined(separator: ",") }.joined(separator: "\r\n") + "\r\n"
    }
}
