import XCTest
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif
@testable import HeotgeoleumCore

/// 지금 목록은 시각이 바뀌었을 때만 본문을 받는다 — 가짜 네트워크(URLProtocol)로 무엇을 물었나 센다
final class CloudCacheTests: XCTestCase {
    final class Stub: URLProtocol {
        nonisolated(unsafe) static var at = "2026-10-02T23:00:00"
        nonisolated(unsafe) static var asked: [String] = []
        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            let q = request.url?.query ?? ""
            Stub.asked.append(q)
            let body = #"{"date":"live","at":"\#(Stub.at)","bikes":[]}"#
            let json = q.contains("body") ? #"[{"at":"\#(Stub.at)","body":\#(body)}]"# : #"[{"at":"\#(Stub.at)"}]"#
            client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(json.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    func testBodyOnlyWhenChanged() async throws {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [Stub.self]
        let sb = SupabaseClient(url: URL(string: "https://cache-test.invalid")!, key: "k", session: URLSession(configuration: cfg))
        Stub.asked = []
        var m = try await sb.live()
        XCTAssertEqual(m.at, "2026-10-02T23:00:00")
        m = try await sb.live()   // 시각 같음 → 시각만 묻고 끝
        XCTAssertEqual(m.at, "2026-10-02T23:00:00")
        Stub.at = "2026-10-02T23:05:00"
        m = try await sb.live()   // 바뀜 → 본문까지
        XCTAssertEqual(m.at, "2026-10-02T23:05:00")
        XCTAssertEqual(Stub.asked, ["select=at,body", "select=at", "select=at", "select=at,body"])
    }
}
