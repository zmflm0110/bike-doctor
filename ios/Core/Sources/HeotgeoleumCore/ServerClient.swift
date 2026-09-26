import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// 맥의 작은 서버(server/app.py)와 주고받기. 같은 모양으로 GitHub 의 live-data 가지(Cloud.data)도 읽는다.
public struct ServerClient: Sendable {
    public static let verdicts = ["체인·기어", "타이어", "안장·핸들", "브레이크", "멀쩡함"]
    public static let surveyStatuses = ["멀쩡함", "타이어", "체인·기어", "안장·핸들", "브레이크", "기타 고장"]

    public let base: URL
    let session: URLSession
    public init(base: URL, session: URLSession = .shared) { self.base = base; self.session = session }

    public enum Failure: Error, Equatable { case rejected(Int), server(Int) }

    public func send(_ path: String, json: [String: Any]? = nil) async throws -> Data {
        var req = URLRequest(url: base.appendingPathComponent(path), cachePolicy: .reloadIgnoringLocalCacheData, timeoutInterval: 10)
        if let json {
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONSerialization.data(withJSONObject: json)
        }
        let (data, code): (Data, Int) = try await withCheckedThrowingContinuation { k in
            session.dataTask(with: req) { d, r, e in
                if let e { k.resume(throwing: e) } else { k.resume(returning: (d ?? Data(), (r as? HTTPURLResponse)?.statusCode ?? 0)) }
            }.resume()
        }
        if code == 400 { throw Failure.rejected(code) }
        guard (200..<300).contains(code) else { throw Failure.server(code) }
        return data
    }

    /// 구조대 확인 → 지금까지 이 자전거를 확인한 사람 수
    public func rescue(bike: String, verdict: String, day: String) async throws -> Int {
        let d = try await send("api/rescue", json: ["bike": bike, "verdict": verdict, "day": day])
        return (try JSONSerialization.jsonObject(with: d) as? [String: Any])?["count"] as? Int ?? 0
    }

    /// 실시간 목록 — 맥 서버의 server/live.py 가 1분마다 쓰는 data/live.json
    public func live() async throws -> MorningList {
        try JSONDecoder().decode(MorningList.self, from: try await send("data/live.json"))
    }

    public func checked() async throws -> Checked {
        try JSONDecoder().decode(Checked.self, from: try await send("api/rescue"))
    }

    public func survey(_ r: SurveyRecord) async throws {
        _ = try await send("api/survey", json: r.json)
    }
}

/// 현장 조사 한 건. 사진은 줄인 JPEG 바이트(선택).
public struct SurveyRecord: Codable, Hashable, Sendable {
    public var station: String
    public var bike: String
    public var status: String
    public var note: String
    public var lat: Double?
    public var lon: Double?
    public var at: Date
    public var photoJPEG: Data?

    public init(station: String, bike: String, status: String, note: String = "", lat: Double? = nil, lon: Double? = nil, at: Date = Date(), photoJPEG: Data? = nil) {
        self.station = station; self.bike = bike; self.status = status; self.note = note; self.lat = lat; self.lon = lon; self.at = at; self.photoJPEG = photoJPEG
    }

    var json: [String: Any] {
        var j: [String: Any] = ["station": station, "bike": bike, "status": status, "note": note, "at": ISO8601DateFormatter().string(from: at)]
        if let lat, let lon { j["lat"] = lat; j["lon"] = lon }
        if let p = photoJPEG { j["photo"] = "data:image/jpeg;base64," + p.base64EncodedString() }
        return j
    }
}

/// 서버에 못 보낸 조사 기록을 기기 파일에 모아 두었다가 다음에 보낸다 (웹앱의 survey_queue 와 같은 규칙):
/// 400(잘못된 기록)은 버리되 사진 때문이면 사진만 빼고 다시, 서버 문제·연결 실패는 남겨 둔다.
public actor SurveyQueue {
    let file: URL
    public private(set) var items: [SurveyRecord]

    public init(file: URL) {
        self.file = file
        items = (try? JSONDecoder().decode([SurveyRecord].self, from: Data(contentsOf: file))) ?? []
    }

    public func add(_ r: SurveyRecord) throws {
        items.append(r)
        try save()
    }

    /// 보내고 남은 건수
    @discardableResult
    public func flush(with client: (any RecordSink)?) async -> Int {
        guard let client else { return items.count }
        var left: [SurveyRecord] = []
        for var r in items {
            do {
                try await client.survey(r)
            } catch ServerClient.Failure.rejected {
                if r.photoJPEG != nil {
                    r.photoJPEG = nil
                    do { try await client.survey(r) } catch ServerClient.Failure.rejected {} catch { left.append(r) }
                }
            } catch {
                left.append(r)
            }
        }
        items = left
        try? save()
        return left.count
    }

    func save() throws {
        try FileManager.default.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONEncoder().encode(items).write(to: file, options: .atomic)
    }
}
