import SwiftUI
import HeotgeoleumCore

@main
struct HeotgeoleumApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .task { await model.start() }
        }
    }
}

struct RootView: View {
    @Environment(AppModel.self) private var model
    @State private var showSettings = false
    // 처음 열 탭 — 실행 인자 `-tab replay` 도 받는다(UserDefaults 인자 영역). 화면 사진·시연용
    @State private var tab = UserDefaults.standard.string(forKey: "tab") ?? "morning"

    var body: some View {
        Group {
            if let error = model.loadError {
                ContentUnavailableView("자료를 못 읽었어요", systemImage: "exclamationmark.triangle", description: Text(error))
            } else if model.store == nil {
                ProgressView("불러오는 중…")
            } else {
                TabView(selection: $tab) {
                    MorningView().tabItem { Label("아침 목록", systemImage: "list.bullet.rectangle") }.tag("morning")
                    LookupView().tabItem { Label("자전거 조회", systemImage: "qrcode.viewfinder") }.tag("lookup")
                    RescueView().tabItem { Label("구조대", systemImage: "hand.raised") }.tag("rescue")
                    ReplayView().tabItem { Label("시연", systemImage: "play.circle") }.tag("replay")
                    SurveyView().tabItem { Label("현장 조사", systemImage: "checklist") }.tag("survey")
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

enum Palette {
    static let accent = Color(red: 15 / 255, green: 118 / 255, blue: 110 / 255)   // #0f766e
    static let red = Color(red: 194 / 255, green: 65 / 255, blue: 12 / 255)       // #c2410c
    static let yellow = Color(red: 217 / 255, green: 154 / 255, blue: 6 / 255)    // #d99a06
    static let good = Color(red: 35 / 255, green: 112 / 255, blue: 50 / 255)      // #237032
    static func level(_ red: Bool) -> Color { red ? Palette.red : Palette.yellow }
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
            .foregroundStyle(red ? .white : .black)
    }
}
