import Foundation

/// 하루 재생 — 시계를 앞으로 돌리면 그 사이 사건을 내놓고 숫자판을 센다. (화면은 이걸 0.1초마다 부른다)
public struct ReplayPlayer: Sendable {
    public let replay: Replay
    public private(set) var clock: Double = 0
    public private(set) var index = 0
    public private(set) var counts: [ReplayEvent.Kind: Int] = [:]
    /// 고장 신고에는 대여소가 없어 마지막으로 본 대여소에 그린다
    public private(set) var lastStation: [String: String] = [:]

    public init(_ replay: Replay) { self.replay = replay }
    public var finished: Bool { index >= replay.events.count }

    /// 헛대여 수(화면의 '헛대여') = 헛대여 + 경보 + 막을 수 있던 헛걸음 (셋 다 헛대여라서)
    public var dudTotal: Int { (counts[.dud] ?? 0) + (counts[.alarm] ?? 0) + (counts[.prevented] ?? 0) }

    public mutating func advance(by seconds: Double) -> [ReplayEvent] {
        clock += seconds
        var out: [ReplayEvent] = []
        while index < replay.events.count, Double(replay.events[index].s) <= clock {
            let e = replay.events[index]
            index += 1
            counts[e.type, default: 0] += 1
            if let st = e.station { lastStation[e.bike] = st }
            out.append(e)
        }
        return out
    }

    public func stationID(for e: ReplayEvent) -> String? { e.station ?? (e.type == .fault ? lastStation[e.bike] : nil) }

    /// "08:15", 다음 날이면 "다음 날 08:15"
    public var clockText: String {
        let c = Int(clock)
        return (c >= 86_400 ? "다음 날 " : "") + String(format: "%02d:%02d", (c / 3600) % 24, (c % 3600) / 60)
    }
}
