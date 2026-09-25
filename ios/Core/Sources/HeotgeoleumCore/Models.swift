import Foundation

/// 대여소 (web/data/stations.json)
public struct Station: Codable, Hashable, Identifiable, Sendable {
    public let id: String
    public var name: String
    public let gu: String
    public let lat: Double
    public let lon: Double
    public var point: GeoPoint { GeoPoint(lat: lat, lon: lon) }
    public init(id: String, name: String, gu: String, lat: Double, lon: Double) {
        self.id = id; self.name = name; self.gu = gu; self.lat = lat; self.lon = lon
    }
}

/// 아침 목록의 의심 자전거 (web/data/morning/<날>.json 의 bikes)
public struct SuspectBike: Codable, Hashable, Identifiable, Sendable {
    public var id: String { bike }
    public let bike: String
    public let station: String
    public var stationName: String
    public let chain: Int
    public let level: String            // "노랑" | "빨강"
    public let lastDud: String
    public let reported: Bool?          // 고장신고 자료가 있을 때만 (시연). 운영·실시간 목록은 모름(nil)
    public let minutesAgo: Int?         // 실시간 목록에만 — 마지막 헛대여가 몇 분 전
    public let truthFirstRiderDud: Bool? // 지난 기록(시연)에만 — 목록이 나온 뒤 처음 빌린 사람도 바로 반납했나
    public var isRed: Bool { level == "빨강" }

    enum CodingKeys: String, CodingKey {
        case bike, station, chain, level, reported
        case stationName = "station_name", lastDud = "last_dud", truthFirstRiderDud = "truth_first_rider_dud", minutesAgo = "minutes_ago"
    }
}

public struct MorningList: Codable, Sendable {
    public let date: String
    public let rule: String?
    public var bikes: [SuspectBike]
    // 실시간 목록(맥 서버의 data/live.json)에만
    public let at: String?
    public let todayAlarms: Int?
    public let score: LiveScore?
    public let feed: FeedStatus?
    enum CodingKeys: String, CodingKey { case date, rule, bikes, at, score, feed, todayAlarms = "today_alarms" }
}

/// 서울 API 가 평소보다 훨씬 적게 내놓는 중인가 (server/live.py feed_status) — 그 사이 새 경보를 놓칠 수 있다
public struct FeedStatus: Codable, Hashable, Sendable {
    public let ok: Bool
    public let since: String?   // "2026-09-25T14:00"
    public let ratio: Double?
    public init(ok: Bool, since: String? = nil, ratio: Double? = nil) { self.ok = ok; self.since = since; self.ratio = ratio }
    /// 알림 문장 — 정상이면 nil
    public var note: String? {
        guard !ok, let since, since.count >= 13, let h = Int(since.dropFirst(11).prefix(2)) else { return nil }
        return "서울시 대여 기록이 \(h)시부터 평소의 \(max(1, Int(((ratio ?? 0) * 100).rounded())))%만 올라오고 있어요. 자료가 늦는 건지 이용이 실제로 줄어든 건지는 아직 몰라요. 그동안 새 경보가 늦을 수 있고, 기록이 다시 들어오면 자동으로 채워요."
    }
}

/// 실시간 경보 채점 — 경보 뒤 처음 빌린 다른 사람도 바로 반납했나 (server/live.py)
public struct LiveScore: Codable, Hashable, Sendable {
    public let alarms: Int?
    public let scored: Int?
    public let nextRiderDud: Int?
    public let precision: Double?
    enum CodingKeys: String, CodingKey { case alarms, scored, nextRiderDud = "next_rider_dud", precision = "precision_%" }
}

/// 운영 중 다음 날 아침 채점 (web/data/morning/scores.json)
public struct DayScore: Codable, Hashable, Sendable {
    public let listed: Int
    public let rode: Int
    public let firstDud: Int
    enum CodingKeys: String, CodingKey { case listed, rode, firstDud = "first_dud" }
}

/// 하루 재생 (web/data/replay_<날>.json)
public struct Replay: Codable, Sendable {
    public let date: String
    public let events: [ReplayEvent]
}

public struct ReplayEvent: Codable, Hashable, Sendable {
    public enum Kind: String, Codable, Sendable {
        case dud = "헛대여", alarm = "경보", prevented = "막을 수 있던 헛걸음", fault = "고장 신고"
    }
    public let s: Int          // 그날 0시부터 초 (다음 날 신고는 86400 넘음)
    public let t: String
    public let type: Kind
    public let bike: String
    public let station: String?
    public let chain: Int?
    public let kind: String?   // 고장 신고 종류
}
