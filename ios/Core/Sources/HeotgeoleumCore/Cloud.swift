import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// 어디서든 — 맥 없이도 앱이 진짜 앱처럼. 웹앱 web/cloud.js 와 같은 값.
///   읽기: GitHub 가 10분마다 만드는 실시간·아침 목록 (.github/workflows/cloud.yml → live-data 가지)
///   쓰기: 구조대 확인·현장 조사 → Supabase (supabase/schema.sql — 누구나 넣기만, 읽기는 자전거별 확인 수만)
public enum Cloud {
    public static let data = URL(string: "https://raw.githubusercontent.com/zmflm0110/bike-doctor/live-data/")!
    public static let supabase = URL(string: "https://iqvquwvoljzuvdgtbpnu.supabase.co")!
    /// 공개(publishable) 키 — 앱에 넣는 용도. 비밀 키(sb_secret·service_role)는 절대 여기 두지 않는다
    public static let supabaseKey = "sb_publishable_YFBKlBvyPFAhBpLdS3o8_A_xIeUmTVE"
}

/// 구조대 확인·현장 조사를 받는 곳 — 맥 서버(ServerClient) 또는 Supabase(SupabaseClient)
public protocol RecordSink: Sendable {
    /// 지금까지 이 자전거를 확인한 사람 수
    func rescue(bike: String, verdict: String, day: String) async throws -> Int
    func checked() async throws -> Checked
    func survey(_ r: SurveyRecord) async throws
}

extension ServerClient: RecordSink {}

public struct SupabaseClient: RecordSink {
    public let url: URL
    public let key: String
    let session: URLSession
    public init(url: URL = Cloud.supabase, key: String = Cloud.supabaseKey, session: URLSession = .shared) {
        self.url = url; self.key = key; self.session = session
    }

    func call(_ path: String, query: String? = nil, body: Data? = nil, contentType: String? = nil) async throws -> Data {
        var c = URLComponents(url: url.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        c.percentEncodedQuery = query
        var req = URLRequest(url: c.url!, timeoutInterval: 15)
        req.setValue(key, forHTTPHeaderField: "apikey")
        if key.hasPrefix("eyJ") { req.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization") }   // 예전 anon 키(JWT)만
        if let body {
            req.httpMethod = "POST"
            req.httpBody = body
            req.setValue(contentType, forHTTPHeaderField: "Content-Type")
            if path.hasPrefix("rest/") { req.setValue("return=minimal", forHTTPHeaderField: "Prefer") }
        }
        let (data, code): (Data, Int) = try await withCheckedThrowingContinuation { k in
            session.dataTask(with: req) { d, r, e in
                if let e { k.resume(throwing: e) } else { k.resume(returning: (d ?? Data(), (r as? HTTPURLResponse)?.statusCode ?? 0)) }
            }.resume()
        }
        // 잘못된 기록(검사 제약·크기·형식)은 버릴 것, 그 밖은 다음에 다시
        if [400, 409, 413, 415, 422].contains(code) { throw ServerClient.Failure.rejected(code) }
        guard (200..<300).contains(code) else { throw ServerClient.Failure.server(code) }
        return data
    }

    public func rescue(bike: String, verdict: String, day: String) async throws -> Int {
        _ = try await call("rest/v1/rescue", body: try JSONSerialization.data(withJSONObject: ["bike": bike, "verdict": verdict, "day": day]),
                           contentType: "application/json")
        return (try await checked(bike: bike)[bike] ?? [:]).values.reduce(0, +)
    }

    public func checked() async throws -> Checked { try await checked(bike: nil) }

    func checked(bike: String?) async throws -> Checked {
        struct Row: Decodable { let bike: String; let verdict: String; let n: Int }
        let rows = try JSONDecoder().decode([Row].self, from: try await call("rest/v1/checked", query: "select=bike,verdict,n" + (bike.map { "&bike=eq.\($0)" } ?? "")))
        var out: Checked = [:]
        for r in rows { out[r.bike, default: [:]][r.verdict] = r.n }
        return out
    }

    /// 사진은 비공개 저장소에 먼저(이름 16자 hex.jpg), 그다음 기록. 사진이 거절되면 rejected — 대기열이 사진만 빼고 다시 보낸다
    public func survey(_ r: SurveyRecord) async throws {
        guard let bike = BikeID.normalize(r.bike) else { throw ServerClient.Failure.rejected(400) }
        var row: [String: Any] = ["at": ISO8601DateFormatter().string(from: r.at), "bike": bike, "status": r.status]
        if let jpeg = r.photoJPEG {
            let name = (0..<8).map { _ in String(format: "%02x", UInt8.random(in: 0...255)) }.joined() + ".jpg"
            _ = try await call("storage/v1/object/survey-photos/\(name)", body: jpeg, contentType: "image/jpeg")
            row["photo"] = name
        }
        if !r.station.isEmpty { row["station"] = String(r.station.prefix(10)) }
        if !r.note.isEmpty { row["note"] = String(r.note.prefix(200)) }
        if let lat = r.lat, let lon = r.lon { row["lat"] = lat; row["lon"] = lon }
        _ = try await call("rest/v1/survey", body: try JSONSerialization.data(withJSONObject: row), contentType: "application/json")
    }
}
