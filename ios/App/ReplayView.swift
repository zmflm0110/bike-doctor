import SwiftUI
import Combine
import MapKit
import HeotgeoleumCore

/// 2026-06-15 하루 재생 — 경보(빨강)·막을 수 있던 헛걸음(초록)·뒤늦은 고장 신고(청록)가 지도에 켜졌다 흐려진다
struct ReplayView: View {
    @Environment(AppModel.self) private var model
    @State private var player: ReplayPlayer?
    @State private var running = false
    @State private var speed = 1800.0          // 초당 몇 초를 돌리나
    @State private var flashes: [Flash] = []
    @State private var feed: [ReplayEvent] = []
    @State private var camera: MapCameraPosition = .region(MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: 37.55, longitude: 126.99),
                                                                              span: MKCoordinateSpan(latitudeDelta: 0.28, longitudeDelta: 0.36)))
    private let tick = Timer.publish(every: 0.1, on: .main, in: .common).autoconnect()

    struct Flash: Identifiable {
        let id = UUID()
        let coordinate: CLLocationCoordinate2D
        let kind: ReplayEvent.Kind
        var life = 1.0
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("2026년 6월 15일,\n서울의 하루를 다시 봐요")
                        .font(.system(size: 26, weight: .bold)).foregroundStyle(Palette.ink)
                        .padding(.horizontal, 4).padding(.top, 8)
                    Text("실제 대여기록을 빠르게 돌려요. 경보가 켜진 자전거를 누가 또 빌렸는지 보세요.").font(.body).foregroundStyle(Palette.sub).padding(.horizontal, 4)
                    Map(position: $camera) {
                        ForEach(flashes) { f in
                            Annotation("", coordinate: f.coordinate, anchor: .center) {
                                Circle().fill(color(f.kind).opacity(0.6 * f.life))
                                    .overlay(Circle().strokeBorder(color(f.kind).opacity(f.life), lineWidth: 2))
                                    .frame(width: f.kind == .alarm ? 18 : 14, height: f.kind == .alarm ? 18 : 14)
                            }
                        }
                    }
                    .mapStyle(.standard(emphasis: .muted, pointsOfInterest: .excludingAll))
                    .environment(\.colorScheme, .dark)
                    .frame(height: 340)
                    .overlay(alignment: .topLeading) {
                        Text(player?.clockText ?? "00:00").font(.system(size: 36, weight: .bold)).monospacedDigit()
                            .foregroundStyle(.white).shadow(color: .black.opacity(0.5), radius: 6).padding(18)
                    }
                    .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                    .padding(.top, 8)
                    .accessibilityLabel("하루 재생 지도 (아래 숫자·기록과 같은 내용)")
                    VStack(spacing: 14) {
                        counter(Palette.sub, "헛대여", player?.dudTotal ?? 0)
                        counter(Palette.red, "경보", player?.counts[.alarm] ?? 0)
                        counter(Palette.good, "막을 수 있던 헛걸음", player?.counts[.prevented] ?? 0)
                        counter(Palette.accent, "뒤늦은 고장 신고", player?.counts[.fault] ?? 0)
                    }
                    .card()
                    if !feed.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(Array(feed.prefix(6).enumerated()), id: \.offset) { _, e in
                                HStack(alignment: .firstTextBaseline, spacing: 10) {
                                    Circle().fill(color(e.type)).frame(width: 7, height: 7)
                                    Text(line(e)).font(.subheadline).foregroundStyle(Palette.body).lineLimit(2)
                                }
                            }
                        }
                        .card()
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 24)
            }
            .screenBackground()
            .safeAreaInset(edge: .bottom) {   // 아래 큰 단추 하나 + 속도
                HStack(spacing: 8) {
                    Button { toggle() } label: {
                        Label(running ? "멈추기" : (player?.finished == true ? "처음부터 다시" : "재생하기"),
                              systemImage: running ? "pause.fill" : (player?.finished == true ? "arrow.counterclockwise" : "play.fill"))
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    Menu {
                        Picker("속도", selection: $speed) {
                            Text("10분/초").tag(600.0); Text("30분/초").tag(1800.0); Text("1시간/초").tag(3600.0); Text("4시간/초").tag(14400.0)
                        }
                    } label: {
                        Text(speedText).font(.subheadline.weight(.semibold)).foregroundStyle(Palette.body)
                            .frame(width: 96, height: 54).background(Palette.card, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    }
                }
                .padding(.horizontal, 16).padding(.vertical, 8)
                .background(Palette.bg.opacity(0.96))
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
            .onReceive(tick) { _ in step() }
            .onAppear {   // 실행 인자 `-autoplay YES` 면 바로 1시간/초로 재생 (화면 사진·시연용)
                if player == nil, UserDefaults.standard.bool(forKey: "autoplay") { speed = 3600; toggle() }
            }
        }
    }

    private func toggle() {
        if running { running = false; return }
        if player == nil || player?.finished == true {
            guard let r = try? model.store?.replay() else { model.show("재생 자료를 못 읽었어요."); return }
            player = ReplayPlayer(r)
            feed = []
            flashes = []
        }
        running = true
    }

    private func step() {
        flashes = flashes.compactMap { var f = $0; f.life -= 1.0 / 30; return f.life > 0 ? f : nil }   // 3초에 걸쳐 흐려짐
        guard running, var p = player else { return }
        let events = p.advance(by: speed / 10)
        for e in events where e.type != .dud {
            if let id = p.stationID(for: e), let s = model.station(id) { flashes.append(Flash(coordinate: s.point.coordinate, kind: e.type)) }
            feed.insert(e, at: 0)
        }
        if feed.count > 60 { feed.removeLast(feed.count - 60) }
        if p.finished { running = false }
        player = p
    }

    private func line(_ e: ReplayEvent) -> String {
        let name = e.station.flatMap { model.station($0)?.name } ?? e.station ?? ""
        switch e.type {
        case .fault: return "\(e.t) 고장 신고 들어옴 — \(e.bike) (\(e.kind ?? "")) · 우리 경보는 이미 울렸음"
        case .alarm: return "\(e.t) 경보 — \(e.bike) 서로 다른 \(e.chain ?? 0)명 연속 (\(name))"
        default: return "\(e.t) 막을 수 있던 헛걸음 — \(e.bike) (\(name))"
        }
    }
    private func color(_ k: ReplayEvent.Kind) -> Color { k == .alarm ? Palette.red : k == .prevented ? Palette.good : Palette.accent }
    private func counter(_ c: Color, _ label: String, _ n: Int) -> some View {
        HStack {
            Circle().fill(c).frame(width: 9, height: 9)
            Text(label).font(.body).foregroundStyle(Palette.body)
            Spacer()
            Text(n.formatted()).font(.title3.weight(.bold)).monospacedDigit().foregroundStyle(Palette.ink).contentTransition(.numericText())
        }
    }
    private var speedText: String { [600.0: "10분/초", 1800: "30분/초", 3600: "1시간/초", 14400: "4시간/초"][speed] ?? "속도" }
}
