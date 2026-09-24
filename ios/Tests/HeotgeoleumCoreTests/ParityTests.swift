import XCTest
@testable import HeotgeoleumCore

/// 아이폰 앱 엔진이 웹앱과 같은 답을 내는지 — 정답은 웹앱에서 뽑은 Fixtures/parity.json (node tests/web/parity_fixture.js)
final class ParityTests: XCTestCase {
    static let repo = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    static let store = try! DataStore(root: repo.appendingPathComponent("web/data"))
    static let fixture: [String: Any] = {
        let url = Bundle.module.url(forResource: "parity", withExtension: "json", subdirectory: "Fixtures")!
        return try! JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
    }()

    func testRankRouteRetroGuMatchWebApp() throws {
        let store = Self.store
        for day in ["2026-06-15", "2026-06-20"] {
            let want = Self.fixture[day] as! [String: Any]
            let bikes = try store.morning(day).bikes
            let groups = Morning.groupByStation(bikes)
            let wantRank = (want["rank"] as! [[String: Any]]).map { ($0["id"] as! String, $0["bikes"] as! [String]) }
            XCTAssertEqual(groups.map(\.id), wantRank.map(\.0), "\(day) 순위")
            XCTAssertEqual(groups.map { $0.bikes.map(\.bike) }, wantRank.map(\.1), "\(day) 대여소 안 순서")

            let r = Morning.route(groups, stations: store.stations, from: nil)
            XCTAssertEqual(r.stops.map(\.id), want["route"] as! [String], "\(day) 동선")
            XCTAssertEqual(r.meters, want["routeMeters"] as! Double, accuracy: 1e-6)

            let here = GeoPoint(lat: 37.5556, lon: 126.9106)
            let n = Morning.route(groups, stations: store.stations, from: here)
            XCTAssertEqual(n.stops.map(\.id), want["nearRoute"] as! [String], "\(day) 내 근처 동선")
            XCTAssertEqual(n.meters, want["nearMeters"] as! Double, accuracy: 1e-6)

            let retro = Morning.retro(bikes), wr = want["retro"] as! [String: Int]
            XCTAssertEqual(retro.known, wr["known"]); XCTAssertEqual(retro.hit, wr["hit"])

            var gu: [String: Int] = [:]
            bikes.forEach { gu[store.gu(of: $0), default: 0] += 1 }
            XCTAssertEqual(gu, want["gu"] as! [String: Int])
        }
    }

    func testRetroNumbersInReport() throws {
        let r = Morning.retro(try Self.store.morning("2026-06-15").bikes)   // 보고서·발표의 "77명 중 29명"
        XCTAssertEqual([r.known, r.hit], [77, 29])
    }

    func testLookupMatchesWebApp() {
        for pair in Self.fixture["lookup"] as! [[Any]] {
            XCTAssertEqual(BikeID.normalize(pair[0] as! String), pair[1] as? String, "\(pair[0])")
        }
    }

    func testStationNamesTrimmedAndDefaultDay() throws {
        XCTAssertFalse(Self.store.stations.values.contains { $0.name.hasPrefix(" ") })
        XCTAssertEqual(Self.store.defaultDay(now: Date(timeIntervalSince1970: 1_790_000_000)), "2026-06-15")   // 2026-09 → 운영 목록 없음
        let f = ISO8601DateFormatter()
        XCTAssertEqual(Self.store.defaultDay(now: f.date(from: "2026-07-02T09:00:00+09:00")!), Self.store.days.last)
    }

    func testCSV() throws {
        let bikes = try Self.store.morning("2026-06-15").bikes.filter { Self.store.gu(of: $0) == "송파구" }
        let csv = Morning.csv(day: "2026-06-15", bikes: bikes, stations: Self.store.stations, checked: [bikes[0].bike: ["타이어": 1]])
        let lines = csv.dropFirst().split(separator: "\r\n")
        XCTAssertTrue(csv.hasPrefix("\u{FEFF}\"기준일\""))
        XCTAssertEqual(lines.count, bikes.count + 1)
        XCTAssertTrue(lines.dropFirst().allSatisfy { $0.contains("\"송파구\"") })
        XCTAssertTrue(csv.contains("\"고장 1/1\""))
    }
}
