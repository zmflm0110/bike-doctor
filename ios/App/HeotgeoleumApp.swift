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
                    MorningView().tabItem { Label("홈", systemImage: "house") }.tag("morning")
                    LookupView().tabItem { Label("조회", systemImage: "magnifyingglass") }.tag("lookup")
                    RescueView().tabItem { Label("확인", systemImage: "heart") }.tag("rescue")
                    ReplayView().tabItem { Label("재생", systemImage: "play.rectangle") }.tag("replay")
                    SurveyView().tabItem { Label("조사", systemImage: "plus.app") }.tag("survey")
                }
                .tint(Palette.accent)
            }
        }
        .overlay(alignment: .bottom) {
            if let t = model.toast {
                Text(t)
                    .font(.subheadline)
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    .padding(.horizontal, 16)
                    .padding(.bottom, 60)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .accessibilityAddTraits(.updatesFrequently)
            }
        }
        .animation(.easeInOut, value: model.toast)
        .sheet(isPresented: $showSettings) { SettingsView() }
        .environment(\.openSettings, { showSettings = true })
    }
}

/// 부드럽고 친근하게 — 우리 청록, 고리 테두리는 청록 그라데이션. 어두운 화면에선 밝은 색 (웹앱 web/style.css 와 같은 값)
enum Palette {
    static func dyn(_ light: UInt32, _ dark: UInt32) -> Color {
        func c(_ h: UInt32) -> UIColor { UIColor(red: CGFloat((h >> 16) & 255) / 255, green: CGFloat((h >> 8) & 255) / 255, blue: CGFloat(h & 255) / 255, alpha: 1) }
        return Color(UIColor { $0.userInterfaceStyle == .dark ? c(dark) : c(light) })
    }
    static let accent = dyn(0x0f766e, 0x2cc5b1)     // 청록
    static let onAccent = dyn(0xffffff, 0x06201d)
    static let red = dyn(0xc2410c, 0xfb8b5d)
    static let redSoft = dyn(0xfdeee6, 0x3a1f15)
    static let yellow = dyn(0xe0a100, 0xf2c14e)
    static let yellowSoft = dyn(0xfff6db, 0x3a300c)
    static let good = dyn(0x237032, 0x6fd08c)
    static let goodSoft = dyn(0xe6f4e8, 0x15301d)
    static let onRed = dyn(0xffffff, 0x2a0e04)
    static let ring = LinearGradient(colors: [0x7ee0cf, 0x2bb3a1, 0x0f766e].map { h in
        Color(red: Double((h >> 16) & 255) / 255, green: Double((h >> 8) & 255) / 255, blue: Double(h & 255) / 255) },
        startPoint: .topLeading, endPoint: .bottomTrailing)
    static func level(_ red: Bool) -> Color { red ? Palette.red : Palette.yellow }
    static func levelSoft(_ red: Bool) -> Color { red ? Palette.redSoft : Palette.yellowSoft }
}

/// 스토리 고리 — 그라데이션 테두리 안에 내용
struct StoryRing<Content: View>: View {
    var size: CGFloat = 64
    var selected = false
    @ViewBuilder var content: () -> Content
    var body: some View {
        Circle().fill(Palette.ring)
            .frame(width: size, height: size)
            .overlay(Circle().fill(Color(.systemBackground)).padding(3).overlay(content()))
            .overlay(Circle().strokeBorder(selected ? Color.primary : .clear, lineWidth: 2).padding(-4))
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
        Button(action: open) { Image(systemName: "gearshape") }.accessibilityLabel("설정")
    }
}

struct LevelTag: View {
    let text: String
    let red: Bool
    var body: some View {
        Text(text)
            .font(.caption.bold())
            .padding(.horizontal, 8).padding(.vertical, 2)
            .background(Palette.level(red), in: Capsule())
            .foregroundStyle(red ? Palette.onRed : Color(red: 0.12, green: 0.09, blue: 0))
    }
}

/// 굵게(**…**)가 들어간 문장 — 문자열 끼워 넣기가 있으면 Text 가 마크다운을 안 읽어서 직접 바꾼다
func md(_ s: String) -> Text {
    Text((try? AttributedString(markdown: s, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace))) ?? AttributedString(s))
}
