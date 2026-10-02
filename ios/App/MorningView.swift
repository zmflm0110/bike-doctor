import SwiftUI
import MapKit
import UniformTypeIdentifiers
import HeotgeoleumCore

/// 홈 — 토스처럼 한 화면에 하나씩: 큰 문장(몇 대) → 구 고르기 → 맞았나 → 지도 → 먼저 볼 곳 → 의심 자전거 몇 대
struct MorningView: View {
    @Environment(AppModel.self) private var model
    @State private var camera: MapCameraPosition = .region(MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: 37.55, longitude: 126.99),
                                                                              span: MKCoordinateSpan(latitudeDelta: 0.28, longitudeDelta: 0.36)))
    @State private var picked: StationGroup?
    @State private var showRoute = false
    @State private var showAll = false
    @State private var allStations = false

    var body: some View {
        let groups = model.groups
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    BrandTitle().padding(.horizontal, 4).padding(.top, 4)
                    hero
                    guChips
                    score
                    StationMap(groups: groups, route: [], here: model.here, camera: $camera, picked: $picked)
                        .frame(height: 260)
                        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
                        .overlay(alignment: .bottomTrailing) {
                            Button { showRoute = true } label: {
                                Label("정비 동선", systemImage: "point.topleft.down.to.point.bottomright.curvepath")
                                    .font(.subheadline.weight(.semibold)).foregroundStyle(Palette.ink)
                                    .padding(.horizontal, 14).padding(.vertical, 10)
                                    .floatingGlass()
                            }
                            .buttonStyle(.plain).padding(12)
                        }
                        .accessibilityLabel("의심 자전거가 있는 대여소 지도 (아래 목록과 같은 내용)")

                    SectionTitle(title: "정비 먼저 볼 곳", sub: model.shown.first?.pNext == nil ? "헛걸음이 많이 쌓인 대여소부터" : "진짜 고장일 자전거가 많을 대여소부터")
                    VStack(spacing: 0) {
                        let top = Array(groups.prefix(allStations ? 10 : 5))
                        ForEach(Array(top.enumerated()), id: \.element.id) { i, g in rankRow(i, g) }
                        if groups.count > 5 {
                            Button { withAnimation { allStations.toggle() } } label: {
                                Text(allStations ? "접기" : "10곳까지 보기").font(.subheadline.weight(.semibold)).foregroundStyle(Palette.sub)
                                    .frame(maxWidth: .infinity, minHeight: 40)
                            }
                        }
                    }
                    .card(padding: 14)
                    SectionTitle(title: "의심 자전거", sub: model.shown.first?.pNext == nil ? "서로 다른 사람들이 연달아 빌리자마자 반납했어요" : "AI 가 본 '다음 사람도 반납할 확률' 순")
                    VStack(spacing: 0) {
                        ForEach(Array(model.shown.prefix(5))) { b in BikeListRow(bike: b) }
                        if model.shown.count > 5 {
                            Button { showAll = true } label: {
                                Text("\(model.shown.count)대 모두 보기").font(.subheadline.weight(.semibold)).foregroundStyle(Palette.sub)
                                    .frame(maxWidth: .infinity, minHeight: 40)
                            }
                        }
                    }
                    .card(padding: 14)
                }
                .padding(.horizontal, 16).padding(.bottom, 32)
            }
            .screenBackground()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    ShareLink(item: model.csv, preview: SharePreview("아침 목록 CSV")) { Image(systemName: "square.and.arrow.up") }
                        .tint(Palette.sub).accessibilityLabel("이 목록을 엑셀용 CSV 로 보내기")
                    SettingsButton()
                }
            }
            .refreshable { await model.refreshChecked() }
            .sheet(item: $picked) { g in StationSheet(group: g).presentationDetents([.medium, .large]) }
            .sheet(isPresented: $showRoute) { RouteSheet().presentationDetents([.large]) }
            .sheet(isPresented: $showAll) { AllBikesSheet() }
            .onChange(of: model.gu) { fit(groups: model.groups) }
        }
    }

    // MARK: 맨 위 — 큰 문장 하나

    private var hero: some View {
        let bikes = model.shown
        let red = bikes.filter(\.isRed).count
        let live = model.day == AppModel.liveDay ? model.morning : nil
        let place = model.gu.isEmpty ? "서울에" : "\(model.gu)에"
        let when = live != nil ? "지금 " : model.isPastData ? "\(AppModel.koDay(model.day)) 아침, " : "오늘 아침, "
        return VStack(alignment: .leading, spacing: 0) {
            dayMenu
            Text("\(when)\(place)\n고장 의심 따릉이가").font(.system(size: 19, weight: .semibold)).foregroundStyle(.white.opacity(0.92))
                .padding(.top, 16)
            HStack(alignment: .firstTextBaseline, spacing: 2) {
                Text("\(bikes.count)").font(.system(size: 64, weight: .heavy, design: .rounded)).monospacedDigit()
                    .contentTransition(.numericText()).animation(.snappy, value: bikes.count)
                Text(model.isPastData ? "대 있었어요" : "대 있어요").font(.system(size: 22, weight: .bold))
            }
            .foregroundStyle(.white)
            Text("빨강 \(red) · 노랑 \(bikes.count - red)\(live?.todayAlarms.map { " · 오늘 경보 \($0)번" } ?? "")")
                .font(.subheadline).foregroundStyle(.white.opacity(0.82)).padding(.top, 6)
            if bikes.count >= 10, let e = ListExpectation(bikes, q: live?.model?.q) {   // 자체 모델: 이 중 진짜 고장일 수 (90% 하한은 docs/model.md)
                HStack(spacing: 6) {
                    Image(systemName: "sparkles").font(.caption.weight(.bold))
                    Text("AI 예측: 이 중 약 \(Int(e.expected.rounded()))대가 진짜 고장 · 최소 \(e.atLeast)대(90%)")
                }
                .font(.footnote.weight(.semibold)).foregroundStyle(.white)
                .padding(.horizontal, 10).padding(.vertical, 6)
                .background(.black.opacity(0.22), in: Capsule())
                .padding(.top, 10)
            }
            ForEach(notes, id: \.self) { n in
                Label(n, systemImage: "hourglass").font(.footnote).foregroundStyle(.white)
                    .padding(.horizontal, 12).padding(.vertical, 8).background(.black.opacity(0.22), in: RoundedRectangle(cornerRadius: 12)).padding(.top, 10)
            }
        }
        .padding(22)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(HeroBackground())
        .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
        .shadow(color: Color(red: 0.086, green: 0.478, blue: 0.4).opacity(0.28), radius: 18, y: 10)
        .padding(.top, 4)
    }

    /// 기준일 — 작은 회색 글씨 단추 (지금 · 5분 전 ▾)
    private var dayMenu: some View {
        Menu {
            Picker("기준일", selection: Binding(get: { model.day }, set: { model.select(day: $0) })) {
                if model.live != nil { Text("지금 (실시간)").tag(AppModel.liveDay) }
                ForEach(model.cloudDays.reversed(), id: \.self) { Text($0 == AppModel.today ? "오늘 아침" : "\(AppModel.koDay($0)) 아침").tag($0) }
                ForEach(model.store?.days ?? [], id: \.self) { Text("\(AppModel.koDay($0)) (시연)").tag($0) }
            }
        } label: {
            HStack(spacing: 6) {
                if model.day == AppModel.liveDay {
                    Circle().fill(Color(red: 0.73, green: 1, blue: 0.91)).frame(width: 7, height: 7)
                    Text("실시간 · \(AppModel.minutesAgo(model.morning?.at ?? ""))분 전")
                } else {
                    Text(model.day == AppModel.today ? "오늘 아침 목록" : "\(AppModel.koDay(model.day)) 자료\(model.cloudLists[model.day] == nil ? " (시연)" : "")")
                }
                Image(systemName: "chevron.down").font(.caption2.weight(.bold))
            }
            .font(.footnote.weight(.semibold)).foregroundStyle(.white)
            .padding(.horizontal, 11).padding(.vertical, 6)
            .background(Color(red: 0.043, green: 0.075, blue: 0.125).opacity(0.28), in: Capsule())
        }
    }

    /// 자료가 늦거나 적게 올 때 알림
    private var notes: [String] {
        guard model.day == AppModel.liveDay, let m = model.morning else { return [] }
        var out: [String] = []
        if let f = m.feed?.note { out.append(f) }
        let ago = AppModel.minutesAgo(m.at ?? "")
        if ago > 30 { out.append("목록 갱신이 늦어지고 있어요(마지막 \(ago)분 전).") }
        return out
    }

    /// 구 고르기 — 알약 (많은 구부터)
    private var guChips: some View {
        let items = [("", "전체", model.morning?.bikes.count ?? 0)] + model.guCounts.sorted { $0.1 > $1.1 }.map { ($0.0, String($0.0.dropLast($0.0.hasSuffix("구") ? 1 : 0)), $0.1) }
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(items, id: \.0) { value, name, count in
                    let on = model.gu == value
                    Button { withAnimation(.snappy) { model.gu = value } } label: {
                        Text("\(name) \(count)")
                            .font(.subheadline.weight(.semibold)).monospacedDigit()
                            .foregroundStyle(on ? Palette.card : Palette.body)
                            .padding(.horizontal, 14).padding(.vertical, 9)
                            .background(on ? Palette.ink : Palette.card, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(value.isEmpty ? "서울 전체" : value) \(count)대")
                }
            }
            .padding(.horizontal, 4)
        }
    }

    // MARK: 맞았나 — 큰 % 하나 + 막대

    @ViewBuilder private var score: some View {
        let r = Morning.retro(model.shown)
        if model.day == AppModel.liveDay, let sc = model.morning?.score, let n = sc.scored, n >= 20 {   // 몇 건으로 낸 % 는 오해를 부른다 — 20건부터
            scoreCard(title: "실시간 경보, 얼마나 맞았을까요?", hit: sc.nextRiderDud ?? 0, of: n, what: "경보 뒤 처음 빌린 다른 사람")
        } else if r.known > 0 {
            scoreCard(title: "이 목록, 얼마나 맞았을까요?", hit: r.hit, of: r.known, what: "목록이 나온 뒤 처음 빌린 사람")
        } else if model.gu.isEmpty, let sc = model.store?.scores[model.day], sc.rode > 0 {
            scoreCard(title: "이 목록, 얼마나 맞았을까요?", hit: sc.firstDud, of: sc.rode, what: "다음 날 첫 이용자")
        }
    }

    private func scoreCard(title: String, hit: Int, of n: Int, what: String) -> some View {
        let p = Double(hit) / Double(max(1, n))
        return HStack(spacing: 16) {
            Ring(value: p)
            VStack(alignment: .leading, spacing: 4) {
                Text(title).font(.headline).foregroundStyle(Palette.ink)
                Text("\(what) \(n.formatted())명 중 \(hit.formatted())명이 또 바로 반납 · 평소 자전거는 2.5%").font(.subheadline).foregroundStyle(Palette.sub)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .card(padding: 18)
    }

    // MARK: 먼저 볼 곳 한 줄

    private func rankRow(_ i: Int, _ g: StationGroup) -> some View {
        let s = model.station(g.id)
        let broken = g.brokenCount(model.checked)
        return Button { picked = g } label: {
            HStack(spacing: 14) {
                Text("\(i + 1)").font(.headline).monospacedDigit()
                    .foregroundStyle(i < 3 ? Palette.accent : Palette.sub)
                    .frame(width: 24)
                VStack(alignment: .leading, spacing: 3) {
                    Text(s?.name ?? g.id).font(.body.weight(.semibold)).foregroundStyle(Palette.ink).lineLimit(1)
                    Text(broken > 0 ? "사람이 확인한 고장 \(broken)대 · \(s?.gu ?? "")"
                         : g.expected.map { "\(s?.gu ?? "") · 진짜 고장 예상 \(String(format: "%.1f", $0))대" } ?? "\(s?.gu ?? "") · 헛걸음 \(g.sumChain)명 쌓임")
                        .font(.subheadline).foregroundStyle(broken > 0 ? Palette.red : Palette.sub).lineLimit(1)
                }
                Spacer(minLength: 8)
                Text("\(g.bikes.count)대").font(.body.weight(.bold)).monospacedDigit().foregroundStyle(Palette.levelText(g.hasRed))
            }
            .padding(.vertical, 10)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func fit(groups: [StationGroup]) {
        let pts = groups.compactMap { model.station($0.id)?.point }
        guard let minLat = pts.map(\.lat).min(), let maxLat = pts.map(\.lat).max(),
              let minLon = pts.map(\.lon).min(), let maxLon = pts.map(\.lon).max() else { return }
        withAnimation {
            camera = .region(MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: (minLat + maxLat) / 2, longitude: (minLon + maxLon) / 2),
                                                span: MKCoordinateSpan(latitudeDelta: max(0.02, (maxLat - minLat) * 1.4), longitudeDelta: max(0.02, (maxLon - minLon) * 1.4))))
        }
    }
}

/// 의심 자전거 한 줄 — 누르면 조회 탭에서 자세히(판정 단추도 거기)
struct BikeListRow: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let bike: SuspectBike
    var body: some View {
        Button {
            model.lookupQuery = bike.bike; model.tab = "lookup"; dismiss()
        } label: {
            ListRow(icon: "bicycle", tint: Palette.levelText(bike.isRed), soft: Palette.levelSoft(bike.isRed),
                    title: bike.bike, subtitle: [bike.stationName, bike.pNext == nil ? nil : "\(bike.chain)명 연속", when].compactMap { $0 }.joined(separator: " · ")) {
                Text(bike.pNext.map { "\($0)%" } ?? "\(bike.chain)명").font(.body.weight(.bold)).monospacedDigit().foregroundStyle(Palette.levelText(bike.isRed))
            }
        }
        .buttonStyle(.plain)
        .accessibilityHint("서로 다른 \(bike.chain)명이 바로 반납\(bike.pNext.map { ", 다음 사람도 반납할 확률 \($0)%" } ?? ""). 누르면 자세히")
    }
    private var when: String? {
        guard let m = bike.minutesAgo else { return nil }
        return m < 60 ? "\(m)분 전" : m < 1440 ? "\(m / 60)시간 전" : "\(m / 1440)일 전"
    }
}

/// 의심 자전거 전부
struct AllBikesSheet: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        NavigationStack {
            ScrollView {
                LazyVStack(spacing: 0) { ForEach(model.shown) { b in BikeListRow(bike: b) } }
                    .card(padding: 14)
                    .padding(16)
            }
            .screenBackground()
            .navigationTitle("의심 자전거 \(model.shown.count)대")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

/// 정비 동선 — 근무 시간을 고르면 막을 헛걸음이 가장 많은 순서 (웹앱 renderRoute 와 같은 규칙)
struct RouteSheet: View {
    @Environment(AppModel.self) private var model
    @State private var shift = 90.0
    @State private var camera: MapCameraPosition = .region(MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: 37.55, longitude: 126.99),
                                                                              span: MKCoordinateSpan(latitudeDelta: 0.28, longitudeDelta: 0.36)))
    @State private var picked: StationGroup?

    var body: some View {
        let route = plan(model.groups)
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Picker("근무 시간", selection: $shift) {
                        Text("1시간").tag(60.0); Text("1시간 30분").tag(90.0); Text("3시간").tag(180.0)
                    }
                    .pickerStyle(.segmented)
                    if let route {
                        (Text("\(route.stops.count)곳을 돌면 헛걸음을\n") + Text("약 \(String(format: "%.1f", route.total))명").foregroundColor(Palette.accent) + Text(" 막아요"))
                            .font(.system(size: 24, weight: .bold)).foregroundStyle(Palette.ink)
                            .padding(.horizontal, 4).padding(.top, 8)
                        Text("약 \(Int(route.used.rounded()))분\(route.total > route.rankTotal + 0.05 ? " · 순위대로 돌 때보다 \(String(format: "%.1f", route.total - route.rankTotal))명 더" : "")")
                            .font(.subheadline).foregroundStyle(Palette.sub).padding(.horizontal, 4)
                        StationMap(groups: model.groups, route: route.stops.map(\.station), here: model.here, camera: $camera, picked: $picked)
                            .frame(height: 220)
                            .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                        stops(route).card(padding: 14)
                    }
                    Button { Task { await model.locate() } } label: { Label(model.here == nil ? "내 위치에서 출발하기" : "내 위치 다시 잡기", systemImage: "location.fill") }
                        .buttonStyle(SoftButtonStyle(tint: Palette.accent))
                }
                .padding(16)
            }
            .screenBackground()
            .navigationTitle("정비 동선")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    typealias PlannedRoute = ValueRoute.Planned

    /// 오늘·실시간이면 지금부터, 지난 날(시연)이면 9시부터
    private func plan(_ groups: [StationGroup]) -> PlannedRoute? {
        guard let store = model.store else { return nil }
        let live = model.day == AppModel.liveDay || model.day == AppModel.today
        let now = Calendar.current.dateComponents(in: TimeZone(identifier: "Asia/Seoul")!, from: Date())
        let t0 = live ? Double((now.hour ?? 9) * 60 + (now.minute ?? 0)) : 540
        return ValueRoute.planGroups(groups, stations: store.stations, busy: store.busy, table: store.routeValue,
                                     here: model.here, minutes: shift, t0: t0)
    }

    private func stops(_ route: PlannedRoute) -> some View {
        func hhmm(_ m: Double) -> String { String(format: "%02d:%02d", Int(m / 60) % 24, Int(m.truncatingRemainder(dividingBy: 60))) }
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(route.stops.enumerated()), id: \.element.group.id) { i, s in
                HStack(spacing: 14) {
                    Text("\(i + 1)").font(.subheadline.weight(.bold)).foregroundStyle(Palette.onAccent)
                        .frame(width: 26, height: 26).background(Palette.accent, in: Circle())
                    VStack(alignment: .leading, spacing: 3) {
                        Text(s.station.name).font(.body.weight(.semibold)).foregroundStyle(Palette.ink).lineLimit(1)
                        Text("\(hhmm(route.arrivals[i])) 도착 · 의심 \(s.group.bikes.count)대").font(.subheadline).foregroundStyle(Palette.sub)
                    }
                    Spacer(minLength: 8)
                    Text("\(String(format: "%.1f", route.values[i]))명").font(.body.weight(.bold)).monospacedDigit().foregroundStyle(Palette.accent)
                }
                .padding(.vertical, 10)
            }
        }
    }
}

struct StationMap: View {
    @Environment(AppModel.self) private var model
    let groups: [StationGroup]
    let route: [Station]
    let here: GeoPoint?
    @Binding var camera: MapCameraPosition
    @Binding var picked: StationGroup?

    var body: some View {
        // 지도 내용에는 if 를 쓰지 않는다 — 없으면 빈 목록으로 (MapContentBuilder 가 받는 모양을 단순하게)
        let placed = groups.compactMap { g in model.station(g.id).map { (g, $0) } }
        let line = ((here.map { [$0] } ?? []) + route.map(\.point)).map(\.coordinate)
        Map(position: $camera) {
            ForEach(placed, id: \.0.id) { g, s in
                Annotation(s.name, coordinate: s.point.coordinate, anchor: .center) {
                    let size = CGFloat(10 + 4 * g.bikes.count)
                    Circle()
                        .fill(Palette.level(g.hasRed).opacity(0.6))
                        .overlay(Circle().strokeBorder(Palette.level(g.hasRed), lineWidth: 1))
                        .frame(width: size, height: size)
                        .onTapGesture { picked = g }
                }
                .annotationTitles(.hidden)
            }
            MapPolyline(coordinates: line.count > 1 ? line : [])
                .stroke(Palette.accent, style: StrokeStyle(lineWidth: 3, dash: [6, 6]))
            ForEach(Array(route.enumerated()), id: \.element.id) { i, s in
                Annotation("", coordinate: s.point.coordinate, anchor: .center) {
                    Text("\(i + 1)").font(.caption2.bold()).foregroundStyle(.white)
                        .frame(width: 20, height: 20).background(Palette.accent, in: Circle())
                }
            }
            ForEach(here.map { [$0] } ?? [], id: \.self) { p in
                Marker("내 위치", systemImage: "location.fill", coordinate: p.coordinate).tint(.blue)
            }
        }
        .mapStyle(.standard(pointsOfInterest: .excludingAll))
    }
}

/// 대여소를 누르면 — 그 대여소의 의심 자전거
struct StationSheet: View {
    @Environment(AppModel.self) private var model
    let group: StationGroup
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) { ForEach(group.bikes) { b in BikeRow(bike: b) } }
                    .card(padding: 14)
                    .padding(16)
            }
            .screenBackground()
            .navigationTitle(model.station(group.id)?.name ?? group.id)
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

/// 대여소 안 자전거 한 줄 — 사람 확인·신고 여부까지
struct BikeRow: View {
    @Environment(AppModel.self) private var model
    let bike: SuspectBike
    var body: some View {
        let c = checkSummary(model.checked, bike: bike.bike)
        let facts = ["서로 다른 \(bike.chain)명 연속", bike.reported.map { $0 ? "신고됨" : "미신고" },
                     c.total == 0 ? nil : c.broken > 0 ? "사람 확인: 고장 \(c.broken)/\(c.total)" : "사람 확인: 멀쩡함 \(c.total)",
                     bike.truthFirstRiderDud.map { $0 ? "다음 사람도 반납" : "다음 사람은 탐" }].compactMap { $0 }
        ListRow(icon: "bicycle", tint: Palette.levelText(bike.isRed), soft: Palette.levelSoft(bike.isRed),
                title: bike.bike, subtitle: facts.joined(separator: " · ")) {
            LevelTag(text: bike.level, red: bike.isRed)
        }
    }
}

extension GeoPoint {
    var coordinate: CLLocationCoordinate2D { CLLocationCoordinate2D(latitude: lat, longitude: lon) }
}

/// ShareLink 로 보내는 CSV — 누를 때 파일을 만든다
struct CSVFile: Transferable {
    let name: String
    let text: String
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(exportedContentType: .commaSeparatedText) { f in
            let url = FileManager.default.temporaryDirectory.appendingPathComponent(f.name)
            try f.text.write(to: url, atomically: true, encoding: .utf8)
            return SentTransferredFile(url)
        }
    }
}
