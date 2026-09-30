import SwiftUI
import HeotgeoleumCore

@main
struct HeotgeoleumApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .task {
                    await model.start()
                    while !Task.isCancelled {   // 실시간 목록 1분마다 (서버 주소가 있을 때만 받음)
                        try? await Task.sleep(for: .seconds(60))
                        await model.refreshLive()
                    }
                }
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var model
    @State private var showSettings = false

    var body: some View {
        Group {
            if let error = model.loadError {
                ContentUnavailableView("자료를 못 읽었어요", systemImage: "exclamationmark.triangle", description: Text(error))
            } else if model.store == nil {
                ProgressView("불러오는 중…")
            } else {
                @Bindable var model = model
                // 아래 탭: 아이콘 + 짧은 이름
                TabView(selection: $model.tab) {
                    MorningView().tabItem { Label("홈", systemImage: "house.fill") }.tag("morning")
                    LookupView().tabItem { Label("조회", systemImage: "magnifyingglass") }.tag("lookup")
                    RescueView().tabItem { Label("확인", systemImage: "checkmark.circle.fill") }.tag("rescue")
                    ReplayView().tabItem { Label("재생", systemImage: "play.rectangle.fill") }.tag("replay")
                    SurveyView().tabItem { Label("조사", systemImage: "square.and.pencil") }.tag("survey")
                }
            }
        }
        .tint(Palette.accent)
        .overlay(alignment: .bottom) {
            if let t = model.toast {
                Text(t)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 18).padding(.vertical, 14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(white: 0.12).opacity(0.94), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .padding(.horizontal, 16)
                    .padding(.bottom, 64)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .accessibilityAddTraits(.updatesFrequently)
            }
        }
        .animation(.easeInOut, value: model.toast)
        .sheet(isPresented: $showSettings) { SettingsView() }
        .environment(\.openSettings, { showSettings = true })
    }
}

/// 토스처럼 — 옅은 회색 바탕 위 테두리 없는 흰 카드, 글자는 짙은 회색 한 가지 + 옅은 회색, 강조색은 로고 청록 하나.
/// 어두운 화면은 로고 남색 바탕. (로고 색: 민트 #35C7A0·청록 #20A68A·남색 #17232E — site/style.css 와 같음)
enum Palette {
    static func dyn(_ light: UInt32, _ dark: UInt32) -> Color {
        func c(_ h: UInt32) -> UIColor { UIColor(red: CGFloat((h >> 16) & 255) / 255, green: CGFloat((h >> 8) & 255) / 255, blue: CGFloat(h & 255) / 255, alpha: 1) }
        return Color(UIColor { $0.userInterfaceStyle == .dark ? c(dark) : c(light) })
    }
    static let accent = dyn(0x167A66, 0x35C7A0)     // 단추·강조 (흰 글자 대비 되는 청록) / 어두운 화면 민트
    static let accentSoft = dyn(0xE3F5EF, 0x123229)
    static let onAccent = dyn(0xFFFFFF, 0x0B1320)
    static let mint = dyn(0x35C7A0, 0x35C7A0)
    static let ink = dyn(0x191F28, 0xF5F7F6)         // 제목·숫자
    static let body = dyn(0x4E5968, 0xB0B8C1)        // 본문
    static let sub = dyn(0x8B95A1, 0x7F8B96)         // 설명
    static let bg = dyn(0xF2F4F6, 0x0B1320)          // 화면 바탕
    static let card = dyn(0xFFFFFF, 0x151E2B)        // 카드
    static let fill = dyn(0xF2F4F6, 0x222D3B)        // 카드 안 회색 단추·입력칸
    static let line = dyn(0xE5E8EB, 0x24313F)        // 나눔선
    static let red = dyn(0xE5484D, 0xFF7A70)
    static let redSoft = dyn(0xFFEEEE, 0x3A1F1F)
    static let yellow = dyn(0xF5A300, 0xF2C14E)
    static let yellowSoft = dyn(0xFFF5DB, 0x3A300C)
    static let yellowText = dyn(0x9A6200, 0xF2C14E)  // 옅은 노랑 위 글자 (대비)
    static let good = dyn(0x15803D, 0x6FD08C)
    static let goodSoft = dyn(0xE6F6EC, 0x15301D)
    /// RIDEY 글자: 민트 → 청록 → 남색 (어두운 화면은 민트 → 흰색) — 사이트 --wgrad 와 같음
    static let wordmark = LinearGradient(colors: [dyn(0x35C7A0, 0x35C7A0), dyn(0x20A68A, 0x7FE0C4), dyn(0x17232E, 0xF5F7F6)], startPoint: .leading, endPoint: .trailing)
    static func level(_ red: Bool) -> Color { red ? Palette.red : Palette.yellow }
    static func levelSoft(_ red: Bool) -> Color { red ? Palette.redSoft : Palette.yellowSoft }
    static func levelText(_ red: Bool) -> Color { red ? Palette.red : Palette.yellowText }
}

extension View {
    /// 흰 카드 — 테두리·그림자 없이 둥글게
    func card(padding: CGFloat = 20) -> some View {
        self.padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.card, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
    }
    /// 화면 바탕
    func screenBackground() -> some View { background(Palette.bg.ignoresSafeArea()) }
}

/// 카드 위 제목 (카드 밖, 바탕 위)
struct SectionTitle: View {
    let title: String
    var sub: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(.title3.weight(.bold)).foregroundStyle(Palette.ink)
            if let sub { Text(sub).font(.subheadline).foregroundStyle(Palette.sub) }
        }
        .padding(.horizontal, 4)
        .padding(.top, 16)
    }
}

/// 목록 한 줄 — 왼쪽 동그란 아이콘, 제목·설명, 오른쪽 값 (토스 목록 모양)
struct ListRow<Trailing: View>: View {
    let icon: String
    var tint: Color = Palette.accent
    var soft: Color = Palette.accentSoft
    let title: String
    var subtitle: String? = nil
    @ViewBuilder var trailing: () -> Trailing
    var body: some View {
        HStack(spacing: 14) {
            Image(systemName: icon).font(.system(size: 17, weight: .semibold)).foregroundStyle(tint)
                .frame(width: 42, height: 42).background(soft, in: Circle())
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.body.weight(.semibold)).foregroundStyle(Palette.ink).lineLimit(1)
                if let subtitle { Text(subtitle).font(.subheadline).foregroundStyle(Palette.sub).lineLimit(1) }
            }
            Spacer(minLength: 8)
            trailing()
        }
        .padding(.vertical, 10)
        .contentShape(Rectangle())
    }
}

/// 빨강·노랑 표시 — 옅은 바탕에 진한 글자
struct LevelTag: View {
    let text: String
    let red: Bool
    var body: some View {
        Text(text)
            .font(.caption.weight(.bold))
            .monospacedDigit()
            .padding(.horizontal, 9).padding(.vertical, 4)
            .background(Palette.levelSoft(red), in: Capsule())
            .foregroundStyle(Palette.levelText(red))
    }
}

/// 큰 단추 (화면 아래 한 개) — 꽉 찬 청록
struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.headline)
            .foregroundStyle(Palette.onAccent)
            .frame(maxWidth: .infinity, minHeight: 54)
            .background(Palette.accent, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .opacity(configuration.isPressed ? 0.85 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// 회색 단추 — 판정·보조 동작
struct SoftButtonStyle: ButtonStyle {
    var tint: Color = Palette.body
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.body.weight(.semibold))
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity, minHeight: 52)
            .background(Palette.fill, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .opacity(configuration.isPressed ? 0.7 : 1)
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .animation(.easeOut(duration: 0.12), value: configuration.isPressed)
    }
}

/// 로고 마크 — 자전거 탄 R (site/img/mark.svg 와 같은 선, 132×92 상자). 바퀴는 남색, 어두운 화면에선 흰색
struct BrandMark: View {
    var height: CGFloat = 24
    var body: some View {
        Canvas { ctx, size in
            let k = size.height / 92
            func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: x * k, y: y * k) }
            for cx in [28.0, 102.0] {
                ctx.stroke(Path(ellipseIn: CGRect(x: (cx - 21) * k, y: 43 * k, width: 42 * k, height: 42 * k)), with: .color(Palette.ink), lineWidth: 12 * k)
                ctx.fill(Path(ellipseIn: CGRect(x: (cx - 4.5) * k, y: 59.5 * k, width: 9 * k, height: 9 * k)), with: .color(Palette.mint))
            }
            var rider = Path()
            rider.move(to: p(42, 13)); rider.addLine(to: p(74, 13)); rider.addCurve(to: p(70, 40), control1: p(92, 13), control2: p(94, 40)); rider.addLine(to: p(60, 40))
            rider.move(to: p(52, 15)); rider.addLine(to: p(30, 62))
            rider.move(to: p(64, 40)); rider.addLine(to: p(100, 62))
            ctx.stroke(rider, with: .linearGradient(Gradient(colors: [Color(red: 0.208, green: 0.78, blue: 0.627), Color(red: 0.125, green: 0.651, blue: 0.541)]),
                                                    startPoint: p(34, 8), endPoint: p(100, 64)),
                       style: StrokeStyle(lineWidth: 14 * k, lineCap: .round, lineJoin: .round))
            ctx.fill(Path(ellipseIn: CGRect(x: 97 * k, y: 5 * k, width: 16 * k, height: 16 * k)), with: .color(Palette.mint))
        }
        .frame(width: height * 132 / 92, height: height)
        .accessibilityHidden(true)
    }
}

/// RIDEY 글자 — RIDE 는 그라데이션, Y 는 남색 줄기 + 민트 체크 (site 의 .ly 와 같은 모양)
struct Wordmark: View {
    var size: CGFloat = 22
    var body: some View {
        HStack(alignment: .lastTextBaseline, spacing: size * 0.02) {
            Text("RIDE").font(.system(size: size, weight: .heavy, design: .rounded)).foregroundStyle(Palette.wordmark)
            Canvas { ctx, s in
                let k = s.height / 70
                var stem = Path(); stem.move(to: CGPoint(x: 4 * k, y: 3 * k)); stem.addLine(to: CGPoint(x: 30 * k, y: 38 * k)); stem.addLine(to: CGPoint(x: 30 * k, y: 68 * k))
                ctx.stroke(stem, with: .color(Palette.ink), style: StrokeStyle(lineWidth: 15 * k, lineJoin: .round))
                var tick = Path(); tick.move(to: CGPoint(x: 36 * k, y: 34 * k)); tick.addLine(to: CGPoint(x: 50 * k, y: 34 * k))
                tick.addLine(to: CGPoint(x: 66 * k, y: 3 * k)); tick.addLine(to: CGPoint(x: 52 * k, y: 3 * k)); tick.closeSubpath()
                ctx.fill(tick, with: .color(Palette.mint))
            }
            .frame(width: size * 0.7 * 66 / 70, height: size * 0.7)
            .alignmentGuide(.lastTextBaseline) { d in d[.bottom] }
        }
        .accessibilityElement().accessibilityLabel("RIDEY")
    }
}

/// 첫 화면 머리: 마크 + RIDEY
struct BrandTitle: View {
    var body: some View {
        HStack(spacing: 8) { BrandMark(height: 22); Wordmark(size: 21) }
    }
}

/// 어느 탭에서든 설정(서버 주소)을 여는 동작
private struct OpenSettingsKey: EnvironmentKey { static let defaultValue: () -> Void = {} }
extension EnvironmentValues {
    var openSettings: () -> Void {
        get { self[OpenSettingsKey.self] }
        set { self[OpenSettingsKey.self] = newValue }
    }
}

/// 탭마다 오른쪽 위 톱니바퀴
struct SettingsButton: View {
    @Environment(\.openSettings) private var open
    var body: some View {
        Button(action: open) { Image(systemName: "gearshape") }.tint(Palette.sub).accessibilityLabel("설정")
    }
}

/// 굵게(**…**)가 들어간 문장 — 문자열 끼워 넣기가 있으면 Text 가 마크다운을 안 읽어서 직접 바꾼다
func md(_ s: String) -> Text {
    Text((try? AttributedString(markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(s))
}
