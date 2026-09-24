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
                    Text("2026년 6월 15일 서울 따릉이 실제 기록을 빠르게 다시 돌립니다.").font(.subheadline).foregroundStyle(.secondary)
                    HStack {
                        Button(running ? "■ 멈춤" : (player?.finished == true ? "▶ 다시" : "▶ 재생")) { toggle() }
                            .buttonStyle(.borderedProminent)
                        Picker("속도", selection: $speed) {
                            Text("10분/초").tag(600.0); Text("30분/초").tag(1800.0); Text("1시간/초").tag(3600.0); Text("4시간/초").tag(14400.0)
                        }.pickerStyle(.menu)
                    }
                    Text(player?.clockText ?? "00:00").font(.system(size: 40, weight: .bold, design: .rounded)).monospacedDigit()
                    Map(position: $camera) {
                        ForEach(flashes) { f in
                            Annotation("", coordinate: f.coordinate, anchor: .center) {
                                Circle().fill(color(f.kind).opacity(0.6 * f.life))
                                    .overlay(Circle().strokeBorder(color(f.kind).opacity(f.life), lineWidth: 2))
                                    .frame(width: f.kind == .alarm ? 18 : 14, height: f.kind == .alarm ? 18 : 14)
                            }
                        }
                    }
                    .mapStyle(.standard(pointsOfInterest: .excludingAll))
                    .frame(height: 300)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .accessibilityLabel("하루 재생 지도 (아래 숫자·기록과 같은 내용)")
                    HStack(spacing: 12) {
                        legend(Palette.red, "경보"); legend(Palette.good, "막을 수 있던 헛걸음"); legend(Palette.accent, "뒤늦은 고장 신고")
                    }.font(.caption)
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        counter(player?.dudTotal ?? 0, "헛대여")
                        counter(player?.counts[.alarm] ?? 0, "경보")
                        counter(player?.counts[.prevented] ?? 0, "막을 수 있던 헛걸음", Palette.good)
                        counter(player?.counts[.fault] ?? 0, "뒤늦은 고장 신고")
                    }
                    ForEach(Array(feed.prefix(30).enumerated()), id: \.offset) { _, e in
                        Text(line(e)).font(.caption).foregroundStyle(e.type == .alarm ? Palette.red : e.type == .prevented ? Palette.good : Palette.accent)
                    }
                }
                .padding(16)
            }
            .navigationTitle("시연")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
            .onReceive(tick) { _ in step() }
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
    private func legend(_ c: Color, _ t: String) -> some View { HStack(spacing: 4) { Circle().fill(c).frame(width: 8, height: 8); Text(t) } }
    private func counter(_ n: Int, _ label: String, _ c: Color = .primary) -> some View {
        VStack { Text("\(n)").font(.title2.bold()).foregroundStyle(c).monospacedDigit(); Text(label).font(.caption).foregroundStyle(.secondary) }
            .frame(maxWidth: .infinity).padding(8)
            .background(.background.secondary, in: RoundedRectangle(cornerRadius: 10))
    }
}
