import SwiftUI
import MapKit
import UniformTypeIdentifiers
import HeotgeoleumCore

struct MorningView: View {
    @Environment(AppModel.self) private var model
    @State private var camera: MapCameraPosition = .region(MKCoordinateRegion(center: CLLocationCoordinate2D(latitude: 37.55, longitude: 126.99),
                                                                              span: MKCoordinateSpan(latitudeDelta: 0.28, longitudeDelta: 0.36)))
    @State private var picked: StationGroup?
    @State private var shift = 90.0   // 정비 동선 근무 시간(분)

    var body: some View {
        let groups = model.groups
        let route = valueRoute(groups)
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    stories
                    filters
                    summary
                    retro
                    StationMap(groups: groups, route: route?.stops.map(\.station) ?? [], here: model.here, camera: $camera, picked: $picked)
                        .frame(height: 300)
                        .clipShape(RoundedRectangle(cornerRadius: 12))
                        .accessibilityLabel("의심 자전거가 있는 대여소 지도 (아래 목록과 같은 내용)")

                    Text("정비 먼저 볼 곳").font(.headline)
                    ForEach(Array(groups.prefix(10))) { g in rankRow(g) }

                    HStack {
                        Text("정비 동선").font(.headline)
                        Text("(근무 시간 안에 헛걸음을 가장 많이 막는 순서)").font(.caption).foregroundStyle(.secondary)
                    }
                    HStack {
                        Picker("근무 시간", selection: $shift) {
                            Text("1시간").tag(60.0); Text("1시간 30분").tag(90.0); Text("3시간").tag(180.0)
                        }.pickerStyle(.segmented)
                        Button { Task { await model.locate() } } label: { Label("내 위치", systemImage: "location") }
                            .buttonStyle(.bordered).buttonBorderShape(.capsule)
                    }
                    if let route { routeList(route) }

                    Text("의심 자전거").font(.headline)
                    ForEach(Array(model.shown.prefix(80))) { b in PostView(bike: b) }
                }
                .padding(16)
            }
            .navigationTitle("헛걸음 제로")
            .toolbar {
                ToolbarItem(placement: .topBarLeading) { dayPicker }
                ToolbarItem(placement: .topBarTrailing) { SettingsButton() }
            }
            .refreshable { await model.refreshChecked() }
            .sheet(item: $picked) { g in StationSheet(group: g).presentationDetents([.medium]) }
            .onChange(of: model.gu) { fit(groups: model.groups) }
        }
    }

    /// 스토리 — 구 고르기. 의심 자전거가 많은 구부터, 고른 구는 테두리
    private var stories: some View {
        let total = model.morning?.bikes.count ?? 0
        let items = [("", "전체", total)] + model.guCounts.sorted { $0.1 > $1.1 }.map { ($0.0, $0.0, $0.1) }
        return ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 14) {
                ForEach(items, id: \.0) { value, name, count in
                    Button { withAnimation { model.gu = value } } label: {
                        VStack(spacing: 6) {
                            StoryRing(size: 64, selected: model.gu == value) {
                                if value.isEmpty { Text("🚲").font(.title2) } else { Text("\(count)").font(.title3.weight(.heavy)) }
                            }
                            Text(value.isEmpty ? name : String(name.dropLast(name.hasSuffix("구") ? 1 : 0))).font(.caption).lineLimit(1)
                        }
                        .frame(width: 70)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(name) \(count)대")
                }
            }
            .padding(.vertical, 4)
        }
    }

    private var filters: some View {
        @Bindable var model = model
        return HStack {
            Picker("구", selection: $model.gu) {
                Text("서울 전체 (\(model.morning?.bikes.count ?? 0)대)").tag("")
                ForEach(model.guCounts, id: \.0) { g, n in Text("\(g) (\(n)대)").tag(g) }
            }
            Spacer()
            ShareLink(item: model.csv, preview: SharePreview("아침 목록 CSV")) { Label("CSV", systemImage: "square.and.arrow.up") }
                .accessibilityLabel("이 목록을 엑셀용 CSV 로 보내기")
        }
        .pickerStyle(.menu)
        .lineLimit(1)
    }

    private var dayPicker: some View {
        Picker("기준일", selection: Binding(get: { model.day }, set: { model.select(day: $0) })) {
            if model.live != nil { Text("지금 (실시간)").tag(AppModel.liveDay) }
            ForEach(model.cloudDays.reversed(), id: \.self) { Text($0 == AppModel.today ? "오늘 아침" : "\(AppModel.koDay($0)) 아침").tag($0) }
            ForEach(model.store?.days ?? [], id: \.self) { Text("\($0) (시연)").tag($0) }
        }
        .pickerStyle(.menu)
        .lineLimit(1)
        .fixedSize()
    }

    private var summary: some View {
        let bikes = model.shown
        let red = bikes.filter(\.isRed).count, unrep = bikes.filter { $0.reported == false }.count, known = bikes.contains { $0.reported != nil }
        if model.day == AppModel.liveDay, let m = model.morning {
            let sc = m.score
            let n = sc?.scored ?? 0   // 몇 건으로 낸 % 는 오해를 부른다 — 20건부터
            let scored = n >= 20 ? "\n실시간 경보 채점: 경보 뒤 처음 빌린 다른 사람 \(n)명 중 **\(sc?.nextRiderDud ?? 0)명**(\(Int((sc?.precision ?? 0).rounded()))%)이 또 바로 반납 (평소 약 2.5%)"
                : n > 0 ? "\n실시간 경보 채점을 모으는 중 (\(n)건 — 20건부터 보여 줘요)" : ""
            let feed = m.feed?.note.map { "\n\n⏳ \($0)" } ?? ""
            return md("\(model.gu.isEmpty ? "" : model.gu + " — ")**지금 \(bikes.count)**대가 서로 다른 사람들이 빌리자마자 반납한 채로 서 있어요 (빨강 \(red)대). \(AppModel.minutesAgo(m.at ?? ""))분 전 갱신 · 오늘 켜진 경보 \(m.todayAlarms ?? 0)번\(scored)\(feed)")
                .font(.subheadline)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.background.secondary, in: RoundedRectangle(cornerRadius: 18))
        }
        let lead = model.gu.isEmpty ? "" : model.gu + " — "
        let body = model.isPastData
            ? "\(AppModel.koDay(model.day)) 아침, **\(bikes.count)**대가 서로 다른 사람들이 빌리자마자 반납한 채로 남아 있었어요 (빨강 \(red)대)."
            : "오늘 아침, **\(bikes.count)**대가 어제까지 서로 다른 사람들이 빌리자마자 반납한 채로 남아 있어요 (빨강 \(red)대)."
        let tail = model.isPastData ? "\n\n📅 지난 자료예요\(model.cloudLists[model.day] == nil ? "(시연용)" : ""). 지금 목록은 맨 위 날짜에서 '지금 (실시간)' 을 고르세요." : ""
        return md(lead + body + (known ? " 이 중 **\(unrep)**대는 아직 아무도 고장 신고를 안 했어요." : "") + tail)
            .font(.subheadline)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(.background.secondary, in: RoundedRectangle(cornerRadius: 18))
    }

    @ViewBuilder private var retro: some View {
        let r = Morning.retro(model.shown)
        if r.known > 0 {
            card("**이 목록은 맞았을까?** (지난 기록이라 채점할 수 있어요) 목록이 나온 뒤 처음 빌린 사람 **\(r.known)**명 중 **\(r.hit)명**(\(Int((100 * Double(r.hit) / Double(r.known)).rounded()))%)이 또 바로 반납했어요. 평소엔 약 2.5% 예요.")
        } else if model.gu.isEmpty, let sc = model.store?.scores[model.day] {
            card("**이 목록은 맞았을까?** 다음 날 아침 채점: 목록 \(sc.listed)대 중 그날 누가 빌린 \(sc.rode)대, 첫 이용자 **\(sc.firstDud)명**이 또 바로 반납했어요. 평소엔 약 2.5% 예요.")
        }
    }

    private func card(_ text: String) -> some View {
        md(text)
            .font(.subheadline)
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.accent.opacity(0.1), in: RoundedRectangle(cornerRadius: 18))
    }

    /// 문자열 속 **굵게** 를 바로 해석 (숫자를 끼워 넣어도 되게)
    private func rankRow(_ g: StationGroup) -> some View {
        let s = model.station(g.id)
        let broken = g.brokenCount(model.checked)
        return Button { picked = g } label: {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(s?.name ?? g.id).bold()
                    Text("\(s?.gu ?? "") · 의심 \(g.bikes.count)대 · 헛걸음 \(g.sumChain)명 누적 (최대 \(g.maxChain)명 연속)")
                        .font(.caption).foregroundStyle(.secondary)
                    if broken > 0 { Text("구조대 확인 고장 \(broken)대").font(.caption.bold()).foregroundStyle(Palette.red) }
                }
                Spacer()
                LevelTag(text: "\(g.bikes.count)", red: g.hasRed)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(10)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 10))
    }

    typealias PlannedRoute = ValueRoute.Planned

    /// 막는 동선 (웹앱 renderRoute 와 같은 규칙): 오늘·실시간이면 지금부터, 지난 날(시연)이면 9시부터
    private func valueRoute(_ groups: [StationGroup]) -> PlannedRoute? {
        guard let store = model.store else { return nil }
        let f = DateFormatter(); f.timeZone = TimeZone(identifier: "Asia/Seoul"); f.dateFormat = "yyyy-MM-dd"
        let live = model.day == AppModel.liveDay || model.day == f.string(from: Date())
        let now = Calendar.current.dateComponents(in: TimeZone(identifier: "Asia/Seoul")!, from: Date())
        let t0 = live ? Double((now.hour ?? 9) * 60 + (now.minute ?? 0)) : 540
        return ValueRoute.planGroups(groups, stations: store.stations, busy: store.busy, table: store.routeValue,
                                     here: model.here, minutes: shift, t0: t0)
    }

    private func routeList(_ route: PlannedRoute) -> some View {
        func hhmm(_ m: Double) -> String { String(format: "%02d:%02d", Int(m / 60) % 24, Int(m.truncatingRemainder(dividingBy: 60))) }
        return VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(route.stops.enumerated()), id: \.element.group.id) { i, s in
                HStack(spacing: 12) {
                    Text("\(i + 1)").font(.subheadline.weight(.heavy)).foregroundStyle(.white)
                        .frame(width: 30, height: 30).background(Palette.accent, in: Circle())
                    VStack(alignment: .leading, spacing: 1) {
                        Text(s.station.name).bold()
                        Text("도착 약 \(hhmm(route.arrivals[i])) · 의심 \(s.group.bikes.count)대 · 막을 헛걸음 예상 \(String(format: "%.1f", route.values[i]))명")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    Spacer()
                    LevelTag(text: "\(s.group.bikes.count)", red: s.group.hasRed)
                }
            }
            (Text("\(model.here == nil ? "" : "내 위치에서 ")\(route.stops.count)곳 · 약 \(Int(route.used.rounded()))분 · 막을 헛걸음 예상 ")
             + Text("\(String(format: "%.1f", route.total))명").bold()
             + Text(route.total > route.rankTotal + 0.05 ? " (순위대로 돌 때보다 \(String(format: "%.1f", route.total - route.rankTotal))명 더)" : ""))
                .font(.caption).foregroundStyle(.secondary)
        }
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

struct StationSheet: View {
    @Environment(AppModel.self) private var model
    let group: StationGroup
    var body: some View {
        NavigationStack {
            List(group.bikes) { b in BikeRow(bike: b) }
                .navigationTitle(model.station(group.id)?.name ?? group.id)
                .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct BikeRow: View {
    @Environment(AppModel.self) private var model
    let bike: SuspectBike
    var body: some View {
        let c = checkSummary(model.checked, bike: bike.bike)
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack { Text(bike.bike).bold(); Text(bike.stationName).font(.caption).foregroundStyle(.secondary) }
                Group {
                    Text("서로 다른 \(bike.chain)명 연속 · 마지막 \(bike.lastDud)") + Text(bike.minutesAgo.map { $0 < 60 ? " (\($0)분 전)" : " (\($0 / 60)시간 전)" } ?? "")
                        + Text(bike.reported.map { $0 ? " · 신고됨" : " · 미신고" } ?? "").bold()
                        + Text(c.total == 0 ? "" : c.broken > 0 ? " · 사람 확인: 고장 \(c.broken)/\(c.total)" : " · 사람 확인: 멀쩡함 \(c.total)")
                        + Text(bike.truthFirstRiderDud == true ? " · 다음 사람도 반납" : bike.truthFirstRiderDud == false ? " · 다음 사람은 탐" : "")
                }
                .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            LevelTag(text: bike.level, red: bike.isRed)
        }
        .padding(10)
        .background(.background.secondary, in: RoundedRectangle(cornerRadius: 10))
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


/// 의심 자전거 하나 = 게시물 하나 (웹앱 bikeRow 와 같은 구성)
struct PostView: View {
    @Environment(AppModel.self) private var model
    let bike: SuspectBike
    var body: some View {
        let c = checkSummary(model.checked, bike: bike.bike)
        let gu = model.station(bike.station)?.gu
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 10) {
                StoryRing(size: 40) { Text("🚲").font(.body) }
                VStack(alignment: .leading, spacing: 1) {
                    Text(bike.bike).font(.subheadline.bold())
                    Text([bike.stationName, gu, when].compactMap { $0 }.joined(separator: " · "))
                        .font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
                Spacer()
                LevelTag(text: bike.level, red: bike.isRed)
            }
            HStack(spacing: 16) {
                Text("\(bike.chain)").font(.system(size: 46, weight: .heavy, design: .rounded)).monospacedDigit()
                    .foregroundStyle(bike.isRed ? Palette.red : Color.primary)
                Text("명이 연달아\n빌리자마자 반납했어요").font(.headline)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 20).padding(.vertical, 18)
            .background(Palette.levelSoft(bike.isRed), in: RoundedRectangle(cornerRadius: 20))
            HStack(spacing: 8) {
                Button { model.focusBike = bike.bike; model.tab = "rescue" } label: { Text("🙋 3초 확인").bold() }
                    .buttonStyle(.borderedProminent).buttonBorderShape(.capsule).tint(Palette.accent)
                Button { model.lookupQuery = bike.bike; model.tab = "lookup" } label: { Text("🔎 자세히").bold() }
                    .buttonStyle(.bordered).buttonBorderShape(.capsule).tint(.primary)
            }
            (Text("서로 다른 \(bike.chain)명 연속 · 마지막 \(bike.lastDud)").foregroundStyle(.secondary)
             + Text(bike.reported.map { $0 ? " · 신고됨" : " · 아직 아무도 신고 안 함" } ?? "").bold()
             + Text(c.total == 0 ? "" : c.broken > 0 ? " · 사람 확인: 고장 \(c.broken)/\(c.total)" : " · 사람 확인: 멀쩡함 \(c.total)")
             + Text(bike.truthFirstRiderDud == true ? " · 다음 사람도 반납" : bike.truthFirstRiderDud == false ? " · 다음 사람은 탐" : ""))
                .font(.footnote)
        }
        .padding(.vertical, 12)
        .overlay(alignment: .bottom) { Divider() }
    }

    private var when: String? {
        guard let m = bike.minutesAgo else { return nil }
        return m < 60 ? "\(m)분 전" : m < 1440 ? "\(m / 60)시간 전" : "\(m / 1440)일 전"
    }
}
