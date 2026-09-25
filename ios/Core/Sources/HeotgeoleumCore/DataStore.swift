import Foundation

/// 앱에 넣은 자료(web/data 를 그대로 복사한 폴더)를 읽는다. 대여소 이름 앞 빈칸은 정리.
public struct DataStore: Sendable {
    public let root: URL
    public let stations: [String: Station]
    public let days: [String]
    public let scores: [String: DayScore]
    /// 정비 동선용 — 대여소 시간대별 대여(busy.json)와 값 표(route_value.json). 없으면 비어 있음(값은 자전거 수로 대신)
    public let busy: Busy
    public let routeValue: RouteValue?

    public init(root: URL) throws {
        self.root = root
        let list = try JSONDecoder().decode([Station].self, from: Data(contentsOf: root.appendingPathComponent("stations.json")))
        var st: [String: Station] = [:]
        for var s in list { s.name = s.name.trimmingCharacters(in: .whitespaces); st[s.id] = s }
        stations = st
        days = try JSONDecoder().decode([String].self, from: Data(contentsOf: root.appendingPathComponent("morning/index.json")))
        scores = (try? JSONDecoder().decode([String: DayScore].self, from: Data(contentsOf: root.appendingPathComponent("morning/scores.json")))) ?? [:]
        busy = (try? JSONDecoder().decode(Busy.self, from: Data(contentsOf: root.appendingPathComponent("busy.json")))) ?? [:]
        routeValue = try? JSONDecoder().decode(RouteValue.self, from: Data(contentsOf: root.appendingPathComponent("route_value.json")))
    }

    public func morning(_ day: String) throws -> MorningList {
        var m = try JSONDecoder().decode(MorningList.self, from: Data(contentsOf: root.appendingPathComponent("morning/\(day).json")))
        for i in m.bikes.indices { m.bikes[i].stationName = m.bikes[i].stationName.trimmingCharacters(in: .whitespaces) }
        return m
    }

    public func replay(_ day: String = "2026-06-15") throws -> Replay {
        try JSONDecoder().decode(Replay.self, from: Data(contentsOf: root.appendingPathComponent("replay_\(day).json")))
    }

    /// 처음 보여 줄 날: 최근 3일 안 목록이면 가장 새 날(운영), 아니면 시연 날짜 6/15 — 웹앱과 같은 규칙
    public func defaultDay(now: Date = Date()) -> String? {
        guard let latest = days.last else { return nil }
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.timeZone = TimeZone(identifier: "Asia/Seoul")
        if let d = f.date(from: latest), now.timeIntervalSince(d) < 3 * 86_400 { return latest }
        return days.contains("2026-06-15") ? "2026-06-15" : latest
    }

    public func gu(of b: SuspectBike) -> String { stations[b.station]?.gu ?? "기타" }
}
