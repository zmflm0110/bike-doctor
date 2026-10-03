import SwiftUI
import HeotgeoleumCore

struct RescueView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let todo = order()
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("의심 자전거 앞에서,\n탭 한 번으로 확인")
                        .font(.system(size: 26, weight: .bold)).foregroundStyle(Palette.ink)
                        .padding(.horizontal, 4).padding(.top, 8)
                    Text("확인 결과는 바로 정비 순위에 반영돼요.").font(.body).foregroundStyle(Palette.sub).padding(.horizontal, 4)

                    if let next = todo.first {
                        VStack(alignment: .leading, spacing: 14) {
                            HStack {
                                LevelTag(text: next.level, red: next.isRed)
                                Spacer()
                                if let d = awayText(next) { Text("\(d) 거리").font(.subheadline.weight(.semibold)).foregroundStyle(Palette.accent) }
                            }
                            VStack(alignment: .leading, spacing: 4) {
                                Text(next.bike).font(.system(size: 28, weight: .bold)).monospacedDigit().foregroundStyle(Palette.ink)
                                Text("\(next.stationName) · 서로 다른 \(next.chain)명이 바로 반납").font(.body).foregroundStyle(Palette.body)
                            }
                            VerdictButtons(bike: next.bike)
                        }
                        .card(padding: 22)
                        .padding(.top, 8)
                        if todo.count > 1 {
                            SectionTitle(title: "그다음")
                            VStack(spacing: 0) {
                                ForEach(Array(todo.dropFirst().prefix(3)), id: \.bike) { b in
                                    ListRow(icon: "bicycle", tint: Palette.levelText(b.isRed), soft: Palette.levelSoft(b.isRed), title: b.bike, subtitle: b.stationName) {
                                        if let d = awayText(b) { Text(d).font(.subheadline.weight(.semibold)).foregroundStyle(Palette.sub) }
                                    }
                                }
                            }
                            .card(padding: 14)
                        }
                    } else {
                        VStack(alignment: .leading, spacing: 10) {
                            Image(systemName: "checkmark.seal.fill").font(.system(size: 36)).foregroundStyle(Palette.good)
                            Text("오늘 목록을 다 확인했어요!").font(.title3.weight(.bold)).foregroundStyle(Palette.ink)
                        }
                        .card(padding: 22)
                    }
                    Button { Task { await model.locate() } } label: { Label(model.here == nil ? "가까운 순서로 보기" : "내 위치 다시 잡기", systemImage: "location.fill") }
                        .buttonStyle(SoftButtonStyle(tint: Palette.accent))

                    SectionTitle(title: "내 확인 기록")
                    if model.rescueLog.isEmpty {
                        Text("아직 없어요. 위에서 한 번 눌러 보세요.").font(.subheadline).foregroundStyle(Palette.sub).padding(.horizontal, 4)
                    } else {
                        VStack(spacing: 0) {
                            ForEach(Array(model.rescueLog.prefix(20))) { x in
                                let fine = x.verdict == "멀쩡함"
                                ListRow(icon: fine ? "checkmark" : "wrench.fill", tint: fine ? Palette.good : Palette.red, soft: fine ? Palette.goodSoft : Palette.redSoft,
                                        title: x.bike, subtitle: x.at.formatted(date: .abbreviated, time: .shortened)) {
                                    Text(x.verdict).font(.subheadline.weight(.semibold)).foregroundStyle(fine ? Palette.good : Palette.red)
                                }
                            }
                        }
                        .card(padding: 14)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 32)
            }
            .screenBackground()
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
        }
    }

    /// 오늘 아직 안 본 자전거 — 위치를 알면 가까운 순 (웹앱과 같은 규칙)
    private func order() -> [SuspectBike] {
        let done = Set(model.rescueLog.filter { $0.day == model.recordDay }.map(\.bike))
        var todo = (model.morning?.bikes ?? []).filter { !done.contains($0.bike) }
        if let f = model.focusBike, let i = todo.firstIndex(where: { $0.bike == f }) {   // 게시물에서 고른 자전거를 맨 앞에
            let b = todo.remove(at: i)
            return [b] + todo
        }
        guard model.here != nil else { return todo }
        return todo.enumerated().sorted { a, b in
            let (da, db) = (distance(a.element) ?? .infinity, distance(b.element) ?? .infinity)
            return da != db ? da < db : a.offset < b.offset
        }.map(\.element)
    }
    private func distance(_ b: SuspectBike) -> Double? {
        guard let here = model.here, let s = model.station(b.station) else { return nil }
        return Geo.meters(here, s.point)
    }
    private func awayText(_ b: SuspectBike) -> String? {
        guard let d = distance(b) else { return nil }
        return d < 1000 ? "\(Int(d.rounded()))m" : String(format: "%.1fkm", d / 1000)
    }
}
