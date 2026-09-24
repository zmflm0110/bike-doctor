import XCTest
@testable import HeotgeoleumCore
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

final class EngineTests: XCTestCase {
    func testRouteLine() {
        // 한 줄로 늘어선 점을 뒤섞어 줘도 끝에서 끝으로 (tests/web/route.test.js 와 같은 검사)
        let line = (0..<8).map { GeoPoint(lat: 37.5, lon: 127 + 0.01 * Double($0)) }
        let shuffled = [5, 1, 7, 3, 0, 6, 2, 4].map { line[$0] }
        let r = Geo.planRoute(from: GeoPoint(lat: 37.5, lon: 126.99), shuffled) { $0 }
        XCTAssertEqual(r, line)
        XCTAssertEqual(Geo.meters(GeoPoint(lat: 37.5, lon: 127), GeoPoint(lat: 37.51, lon: 127)), 1112, accuracy: 5)
        XCTAssertTrue(Geo.planRoute(from: line[0], [GeoPoint]()) { $0 }.isEmpty)
    }

    func testRankPutsHumanConfirmedFirst() {
        func b(_ id: String, _ st: String, _ chain: Int) -> SuspectBike {
            try! JSONDecoder().decode(SuspectBike.self, from: """
            {"bike":"\(id)","station":"\(st)","station_name":"x","chain":\(chain),"level":"노랑","last_dud":"06-14 23:30","reported":false}
            """.data(using: .utf8)!)
        }
        let bikes = [b("SPB-00001", "0A", 9), b("SPB-00002", "0B", 2)]
        XCTAssertEqual(Morning.groupByStation(bikes).map(\.id), ["0A", "0B"])
        XCTAssertEqual(Morning.groupByStation(bikes, checked: ["SPB-00002": ["타이어": 1]]).map(\.id), ["0B", "0A"])
        XCTAssertEqual(Morning.groupByStation(bikes, checked: ["SPB-00002": ["멀쩡함": 2]]).map(\.id), ["0A", "0B"])
        // 자바스크립트 객체 키 순서 흉내: 앞자리 0 없는 번호는 작은 수부터 먼저
        let tie = [b("SPB-1", "02720", 2), b("SPB-2", "3000", 2), b("SPB-3", "150", 2)]
        XCTAssertEqual(Morning.groupByStation(tie).map(\.id), ["150", "3000", "02720"])
    }

    func testReplay() throws {
        let replay = try ParityTests.store.replay()
        var p = ReplayPlayer(replay)
        var seen = 0
        while !p.finished { seen += p.advance(by: 3600).count }
        XCTAssertEqual(seen, replay.events.count)
        XCTAssertEqual(p.counts[.alarm], 314); XCTAssertEqual(p.counts[.prevented], 324); XCTAssertEqual(p.counts[.fault], 84)
        XCTAssertEqual(p.dudTotal, 3447 + 314 + 324)
        XCTAssertTrue(p.clockText.hasPrefix("다음 날"))
        var q = ReplayPlayer(replay)
        _ = q.advance(by: 9 * 3600)
        XCTAssertEqual(q.clockText, "09:00")
        let fault = replay.events.first { $0.type == .fault && q.lastStation[$0.bike] != nil }
        if let fault { XCTAssertNotNil(q.stationID(for: fault)) }
    }
}

/// 가짜 서버 (URLProtocol) — 조사 기록 대기열이 웹앱과 같은 규칙으로 보내고 남기는지
final class FakeServer: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest, [String: Any]) -> Int)!
    nonisolated(unsafe) static var got: [[String: Any]] = []
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var body = request.httpBody
        if body == nil, let s = request.httpBodyStream {
            s.open(); var d = Data(); var buf = [UInt8](repeating: 0, count: 65536)
            while s.hasBytesAvailable { let n = s.read(&buf, maxLength: buf.count); if n <= 0 { break }; d.append(buf, count: n) }
            s.close(); body = d
        }
        let json = body.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        Self.got.append(json)
        let code = Self.handler(request, json)
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: code, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: code == 200 ? #"{"ok":true,"count":3,"total":1}"#.data(using: .utf8)! : Data())
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class QueueTests: XCTestCase {
    func client() -> ServerClient {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [FakeServer.self]
        return ServerClient(base: URL(string: "http://mac.local:8765/")!, session: URLSession(configuration: cfg))
    }

    func testQueueRules() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathComponent("q.json")
        let q = SurveyQueue(file: file)
        try await q.add(SurveyRecord(station: "02720", bike: "SPB-00001", status: "타이어", photoJPEG: Data([0xFF, 0xD8, 0xFF])))  // 사진 거절 → 사진 빼고 성공
        try await q.add(SurveyRecord(station: "02720", bike: "SPB-00002", status: "멀쩡함"))                                        // 서버 문제 → 남김
        try await q.add(SurveyRecord(station: "02720", bike: "SPB-00003", status: "모름"))                                          // 잘못된 기록 → 버림
        FakeServer.got = []
        FakeServer.handler = { _, j in
            if j["photo"] != nil { return 400 }
            if j["bike"] as? String == "SPB-00002" { return 500 }
            if j["status"] as? String == "모름" { return 400 }
            return 200
        }
        let left = await q.flush(with: client())
        XCTAssertEqual(left, 1)
        let remaining = await q.items.map(\.bike)
        XCTAssertEqual(remaining, ["SPB-00002"])
        XCTAssertEqual(FakeServer.got.count, 4)   // 사진 있는 것 한 번 + 사진 빼고 한 번 + 둘
        XCTAssertTrue((FakeServer.got[0]["photo"] as? String)?.hasPrefix("data:image/jpeg;base64,") == true)
        XCTAssertNil(FakeServer.got[1]["photo"])
        // 다시 열어도 남은 것이 그대로 (파일에 저장)
        let reopened = await SurveyQueue(file: file).items.map(\.bike)
        XCTAssertEqual(reopened, ["SPB-00002"])
        let noServer = await q.flush(with: nil)
        XCTAssertEqual(noServer, 1)   // 서버 없음 → 그대로
    }

    func testRescue() async throws {
        FakeServer.handler = { r, j in (r.url!.path == "/api/rescue" && j["verdict"] as? String == "타이어") ? 200 : 400 }
        let n = try await client().rescue(bike: "SPB-00001", verdict: "타이어", day: "2026-06-15")
        XCTAssertEqual(n, 3)
        do { _ = try await client().rescue(bike: "SPB-00001", verdict: "폭탄", day: ""); XCTFail() }
        catch ServerClient.Failure.rejected {}
    }
}
