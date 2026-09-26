import XCTest
@testable import HeotgeoleumCore

/// 진짜 클라우드에 닿는 검사 — 평소엔 건너뛴다. `SUPABASE_IT=1 swift test --filter CloudLiveTests`
/// (시험 기록은 SPB-99996 으로 넣고, 끝나면 DB 비밀번호로 지운다: psql … "delete from rescue/survey where bike='SPB-99996'")
final class CloudLiveTests: XCTestCase {
    func testSupabaseAndLiveData() async throws {
        try XCTSkipUnless(ProcessInfo.processInfo.environment["SUPABASE_IT"] == "1", "SUPABASE_IT=1 일 때만")
        let sb = SupabaseClient()
        let n = try await sb.rescue(bike: "SPB-99996", verdict: "타이어", day: "2026-09-26")
        XCTAssertGreaterThanOrEqual(n, 1)
        try await sb.survey(SurveyRecord(station: "00102", bike: "spb 99996", status: "체인·기어", note: "앱 연결 시험(곧 지움)", lat: 37.55, lon: 126.91))
        let checked = try await sb.checked()
        XCTAssertGreaterThanOrEqual(checked["SPB-99996"]?.values.reduce(0, +) ?? 0, 2)
        let live = try await ServerClient(base: Cloud.data).live()
        XCTAssertNotNil(live.at)
        XCTAssertFalse(live.bikes.isEmpty)
    }
}
