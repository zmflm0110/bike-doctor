import SwiftUI
import HeotgeoleumCore

struct RescueView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        let todo = order()
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("근처 의심 자전거를 3초만 봐 주세요. 확인 결과는 정비로 이어집니다.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    Button { Task { await model.locate() } } label: {
                        Label("가까운 순서로", systemImage: "location").frame(maxWidth: .infinity)
                    }.buttonStyle(.bordered)

                    if let next = todo.first {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("\(next.stationName)의 \(next.bike)\(away(next))").font(.title3.bold()).foregroundStyle(Palette.red)
                            Text("서로 다른 \(next.chain)명이 바로 반납했어요. 가까이 있다면 3초만 봐 주세요.")
                            VerdictButtons(bike: next.bike)
                        }
                        .padding(18)
                        .background(Palette.redSoft, in: RoundedRectangle(cornerRadius: 20))
                        if todo.count > 1 {
                            Text("그다음: " + todo.dropFirst().prefix(3).map { "\($0.stationName) \($0.bike)\(away($0))" }.joined(separator: " · "))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    } else {
                        Label("오늘 목록을 다 확인했어요!", systemImage: "checkmark.seal.fill").foregroundStyle(Palette.good)
                    }

                    Text("내 구조 기록").font(.headline).padding(.top, 8)
                    ForEach(model.rescueLog.prefix(20)) { x in
                        HStack {
                            VStack(alignment: .leading) {
                                Text(x.bike).bold()
                                Text(x.at.formatted(date: .abbreviated, time: .shortened)).font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            LevelTag(text: x.verdict, red: x.verdict != "멀쩡함")
                        }
                        .padding(.vertical, 8)
                    }
                }
                .padding(16)
            }
            .navigationTitle("구조대")
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
    private func away(_ b: SuspectBike) -> String {
        guard let d = distance(b) else { return "" }
        return d < 1000 ? " · \(Int(d.rounded()))m" : String(format: " · %.1fkm", d / 1000)
    }
}
