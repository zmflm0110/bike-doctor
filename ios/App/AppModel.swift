import Foundation
import Observation
import CoreLocation
import HeotgeoleumCore

/// 앱 전체 상태 — 자료(앱에 넣은 web/data), 고른 날·구, 사람 확인, 내 위치, 서버, 조사 대기열.
@Observable
@MainActor
final class AppModel {
    var store: DataStore?
    var loadError: String?
    private(set) var day: String = ""
    var morning: MorningList?
    /// 실시간 목록 (맥 서버의 data/live.json, 1분마다). 서버 주소가 없거나 20분 넘게 안 바뀌었으면 nil.
    var live: MorningList?
    static let liveDay = "지금"
    var gu: String = ""
    var checked: Checked = [:]
    var here: GeoPoint?
    var toast: String?
    var queued = 0
    /// 지금 탭 — 실행 인자 `-tab replay` 도 받는다(화면 사진·시연용). 게시물 단추가 다른 탭으로 보낼 때 바꾼다
    var tab: String = UserDefaults.standard.string(forKey: "tab") ?? "morning"
    /// 게시물의 '3초 확인' 으로 고른 자전거 → 확인 탭 맨 앞 / '자세히' → 조회 탭에 넣을 번호
    var focusBike: String?
    var lookupQuery: String?
    var rescueLog: [RescueEntry] = RescueEntry.load()

    /// 집 맥 서버 주소 (선택, 예: http://내맥.local:8765) — 같은 와이파이면 1분마다 갱신되는 목록. 없어도 앱은 어디서든 돈다(Cloud).
    var serverURL: String = UserDefaults.standard.string(forKey: "serverURL") ?? ""
    func saveServer() {
        UserDefaults.standard.set(serverURL, forKey: "serverURL")
        Task { queued = await queue.flush(with: sink); await refreshChecked() }
    }
    var client: ServerClient? {
        guard let u = URL(string: serverURL.trimmingCharacters(in: .whitespaces)), u.scheme?.hasPrefix("http") == true else { return nil }
        return ServerClient(base: u)
    }
    /// 구조대 확인·현장 조사를 보내는 곳 — 어디서든 Supabase (키가 없으면 맥 서버)
    var sink: (any RecordSink)? { Cloud.supabaseKey.isEmpty ? client : SupabaseClient() }
    /// GitHub 가 10분마다 만드는 목록 (live-data 가지)
    let cloud = ServerClient(base: Cloud.data)
    /// GitHub 가 매일 06:10 만든 아침 목록 (최근 7일) — 앱에 넣은 시연 자료보다 먼저 보인다
    var cloudLists: [String: MorningList] = [:]
    var cloudDays: [String] { cloudLists.keys.sorted() }

    let queue = SurveyQueue(file: URL.documentsDirectory.appendingPathComponent("survey_queue.json"))
    private let locator = Locator()

    func start() async {
        guard store == nil else { return }
        do {
            guard let root = Bundle.main.url(forResource: "data", withExtension: nil) else { throw CocoaError(.fileNoSuchFile) }
            let s = try DataStore(root: root)
            store = s
            select(day: UserDefaults.standard.string(forKey: "day") ?? s.defaultDay() ?? "")   // 실행 인자 -day 2026-06-15 로 고정 가능
        } catch {
            loadError = "앱 안의 자료(data 폴더)를 읽지 못했어요: \(error.localizedDescription)"
        }
        queued = await queue.flush(with: sink)
        await refreshChecked()
        await refreshCloudDays()
        await refreshLive()
        if UserDefaults.standard.string(forKey: "day") == nil {   // -day 인자로 고정하지 않았으면: 실시간 → 오늘 아침 목록 → 시연 자료
            if live != nil { select(day: Self.liveDay) } else if let d = cloudDays.last, d == Self.today { select(day: d) }
        }
    }

    /// 오늘(서울) 'YYYY-MM-DD'
    static var today: String {
        let f = DateFormatter(); f.timeZone = TimeZone(identifier: "Asia/Seoul"); f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Date())
    }

    /// GitHub 의 최근 아침 목록 받기 (없거나 밖이 아니어도 조용히 넘어감)
    func refreshCloudDays() async {
        guard let d = try? await cloud.send("data/ops/index.json"), let days = try? JSONDecoder().decode([String].self, from: d) else { return }
        for day in days.suffix(7) where cloudLists[day] == nil {
            if let data = try? await cloud.send("data/ops/\(day).json"), var m = try? JSONDecoder().decode(MorningList.self, from: data) {
                for i in m.bikes.indices { m.bikes[i].stationName = m.bikes[i].stationName.trimmingCharacters(in: .whitespaces) }
                cloudLists[day] = m
            }
        }
    }

    /// 맥 서버 연결 상태 — 설정의 '연결 확인' 과 조회 안내에 쓴다. nil = 주소 없음
    var serverStatus: String?

    /// 실시간 목록 다시 받기 — 화면이 1분마다 부른다. 집 맥(1분 간격, 같은 와이파이)과 GitHub(10분 간격, 어디서든) 중 더 새 것
    func refreshLive() async {
        let (mc, cc) = (client, cloud)   // 메인 액터 밖에서 동시에 받으려고 값으로 꺼냄
        async let mac: MorningList? = { guard let mc else { return nil }; return try? await mc.live() }()
        async let web: MorningList? = try? await cc.live()
        let (m, w) = await (mac, web)
        let fresh = [(m, 20, "집 맥"), (w, 45, "클라우드")].compactMap { x, limit, name -> (MorningList, Int, String)? in
            guard let x, let at = x.at else { return nil }
            let ago = Self.minutesAgo(at)
            return ago <= limit ? (x, ago, name) : nil
        }.min { $0.1 < $1.1 }
        guard let (best, ago, name) = fresh else {
            serverStatus = client == nil ? "실시간 목록을 받지 못했어요 — 인터넷 연결을 확인해 주세요." :
                "집 맥에도, 클라우드에도 닿지 않거나 목록이 오래됐어요 — 인터넷 연결을 확인해 주세요."
            if live != nil { live = nil; if day == Self.liveDay { select(day: cloudDays.last ?? store?.defaultDay() ?? "") } }
            return
        }
        serverStatus = "연결됨 · \(name) · 지금 의심 \(best.bikes.count)대 (\(ago)분 전 갱신)"
        live = best
        liveSource = name
        if day == Self.liveDay { morning = best }
    }
    /// 지금 목록이 어디서 왔나 — "집 맥" (1분마다) / "클라우드" (10분마다)
    var liveSource = ""

    /// 시연(지난) 자료를 보고 있나 — 실시간이 아니면 앱에 넣은 지난 날의 아침 목록이다
    var isPastData: Bool { day != Self.liveDay && day != Self.today }
    /// "2026-06-15" → "6월 15일"
    static func koDay(_ d: String) -> String {
        let p = d.split(separator: "-").compactMap { Int($0) }
        return p.count == 3 ? "\(p[1])월 \(p[2])일" : d
    }

    /// 'YYYY-MM-DDTHH:MM:SS'(서울 시각) → 지금부터 몇 분 전
    static func minutesAgo(_ iso: String) -> Int {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX"); f.timeZone = TimeZone(identifier: "Asia/Seoul")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        guard let d = f.date(from: iso) else { return .max }
        return max(0, Int(Date().timeIntervalSince(d) / 60))
    }

    /// 기록에 남길 날짜 — 실시간이면 오늘
    var recordDay: String {
        guard day == Self.liveDay else { return day }
        let f = DateFormatter(); f.timeZone = TimeZone(identifier: "Asia/Seoul"); f.dateFormat = "yyyy-MM-dd"
        return f.string(from: Date())
    }

    func select(day d: String) {
        day = d
        guard let store, !day.isEmpty else { return }
        morning = day == Self.liveDay ? live : (cloudLists[day] ?? (try? store.morning(day)))
        if !gu.isEmpty, !(morning?.bikes.contains { store.gu(of: $0) == gu } ?? false) { gu = "" }
    }

    // MARK: 아침 목록

    var shown: [SuspectBike] {
        guard let store, let m = morning else { return [] }
        return gu.isEmpty ? m.bikes : m.bikes.filter { store.gu(of: $0) == gu }
    }
    var groups: [StationGroup] { Morning.groupByStation(shown, checked: checked) }
    var guCounts: [(String, Int)] {
        guard let store, let m = morning else { return [] }
        var n: [String: Int] = [:]
        m.bikes.forEach { n[store.gu(of: $0), default: 0] += 1 }
        return n.sorted { $0.key.compare($1.key, locale: Locale(identifier: "ko_KR")) == .orderedAscending }.map { ($0.key, $0.value) }
    }
    func station(_ id: String) -> Station? { store?.stations[id] }

    /// 정비 담당용 CSV (엑셀용, 이름은 영문 — 웹앱과 같음)
    var csv: CSVFile {
        CSVFile(name: "morning_\(day == Self.liveDay ? "live" : day)\(gu.isEmpty ? "" : "_" + (GuNames.english[gu] ?? "gu")).csv",
                text: store.map { Morning.csv(day: recordDay, bikes: shown, stations: $0.stations, checked: checked) } ?? "")
    }

    // MARK: 위치

    /// 한 번 받기. 실패하면 알림 뒤 nil.
    @discardableResult
    func locate() async -> GeoPoint? {
        do {
            let c = try await locator.once()
            here = GeoPoint(lat: c.latitude, lon: c.longitude)
        } catch {
            show("위치를 쓸 수 없어요. 설정 → 개인정보 보호 → 위치 서비스에서 허용해 주세요.")
        }
        return here
    }

    // MARK: 구조대·서버

    func refreshChecked() async {
        guard let sink else { return }
        if let c = try? await sink.checked() { checked = c }
    }

    func rescue(_ bike: String, _ verdict: String) async {
        if focusBike == bike { focusBike = nil }
        rescueLog.insert(RescueEntry(bike: bike, verdict: verdict, day: recordDay, at: Date()), at: 0)
        RescueEntry.save(rescueLog)
        var sent = ""
        if let sink, let n = try? await sink.rescue(bike: bike, verdict: verdict, day: recordDay) {
            sent = " 지금까지 \(n)명이 이 자전거를 확인했어요."
            await refreshChecked()
        }
        show("고마워요! \(bike) 를 \"\(verdict)\" 로 기록했어요.\(sent)")
    }

    func survey(_ r: SurveyRecord) async {
        do { try await queue.add(r) } catch { show("기기에 저장하지 못했어요: \(error.localizedDescription)"); return }
        queued = await queue.flush(with: sink)
        await refreshChecked()
        show("\(r.bike) → \(r.status)\(r.photoJPEG != nil ? " (사진 포함)" : "")\(queued > 0 ? " — 서버에 못 보낸 \(queued)건은 폰에 보관 중" : "")")
    }

    func show(_ text: String) {
        toast = text
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(3.2))
            if toast == text { toast = nil }
        }
    }
}

struct RescueEntry: Codable, Identifiable, Hashable {
    var id: String { bike + at.description }
    let bike: String
    let verdict: String
    let day: String
    let at: Date

    static func load() -> [RescueEntry] {
        guard let d = UserDefaults.standard.data(forKey: "rescue") else { return [] }
        return (try? JSONDecoder().decode([RescueEntry].self, from: d)) ?? []
    }
    static func save(_ log: [RescueEntry]) {
        UserDefaults.standard.set(try? JSONEncoder().encode(Array(log.prefix(200))), forKey: "rescue")
    }
}

/// CLLocationManager 를 async 한 번 받기로
final class Locator: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var waiting: [CheckedContinuation<CLLocationCoordinate2D, Error>] = []

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
    }

    @MainActor
    func once() async throws -> CLLocationCoordinate2D {
        try await withCheckedThrowingContinuation { k in
            waiting.append(k)
            switch manager.authorizationStatus {
            case .notDetermined: manager.requestWhenInUseAuthorization()
            case .denied, .restricted: finish(.failure(CLError(.denied)))
            default: manager.requestLocation()
            }
        }
    }

    private func finish(_ r: Result<CLLocationCoordinate2D, Error>) {
        let w = waiting
        waiting = []
        w.forEach { $0.resume(with: r) }
    }

    func locationManagerDidChangeAuthorization(_ m: CLLocationManager) {
        guard !waiting.isEmpty else { return }
        switch m.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: m.requestLocation()
        case .denied, .restricted: finish(.failure(CLError(.denied)))
        default: break
        }
    }
    func locationManager(_ m: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        if let c = locations.last?.coordinate { finish(.success(c)) }
    }
    func locationManager(_ m: CLLocationManager, didFailWithError error: Error) { finish(.failure(error)) }
}

enum GuNames {
    static let english: [String: String] = [
        "강남구": "gangnam", "강동구": "gangdong", "강북구": "gangbuk", "강서구": "gangseo", "관악구": "gwanak", "광진구": "gwangjin", "구로구": "guro",
        "금천구": "geumcheon", "노원구": "nowon", "도봉구": "dobong", "동대문구": "dongdaemun", "동작구": "dongjak", "마포구": "mapo", "서대문구": "seodaemun",
        "서초구": "seocho", "성동구": "seongdong", "성북구": "seongbuk", "송파구": "songpa", "양천구": "yangcheon", "영등포구": "yeongdeungpo", "용산구": "yongsan",
        "은평구": "eunpyeong", "종로구": "jongno", "중구": "jung", "중랑구": "jungnang",
    ]
}
