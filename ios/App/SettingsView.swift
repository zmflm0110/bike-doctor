import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var checking = false

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                Section {
                    TextField("http://내맥이름.local:8765", text: $model.serverURL)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                } header: {
                    Text("집 맥 서버 (선택)")
                    Button(checking ? "확인하는 중…" : "연결 확인") {
                        Task { checking = true; model.saveServer(); await model.refreshLive(); checking = false }
                    }
                    .disabled(checking)
                    if let s = model.serverStatus { Text(s).font(.footnote) }
                } footer: {
                    Text("없어도 됩니다 — 앱은 어디서든 클라우드(10분마다 갱신)로 돌고, 구조대 확인·현장 조사는 클라우드 DB 로 바로 갑니다(인터넷이 없으면 폰에 보관했다가 나중에). 집 와이파이에서 맥 서버를 켜 두면 1분마다 갱신되는 목록을 먼저 씁니다: 맥의 '시스템 설정 → 일반 → 공유' 맨 아래 이름 뒤에 .local:8765 (예: http://내맥이름.local:8765).")
                }
                Section("자료") {
                    LabeledContent("지금 목록", value: model.live == nil ? "못 받음" : "\(model.liveSource) · \(AppModel.minutesAgo(model.live?.at ?? ""))분 전")
                    LabeledContent("매일 아침 목록 (클라우드)", value: model.cloudDays.isEmpty ? "아직 없음" : "\(model.cloudDays.count)일 (~ \(model.cloudDays.last ?? ""))")
                    LabeledContent("시연 자료 (앱 안)", value: "\(model.store?.days.count ?? 0)일 (\(model.store?.days.first ?? "") ~ \(model.store?.days.last ?? ""))")
                    LabeledContent("대여소", value: "\(model.store?.stations.count ?? 0)곳")
                    LabeledContent("보관 중인 조사 기록", value: "\(model.queued)건")
                }
                Section {
                    Text("서울 열린데이터광장 따릉이 대여이력·고장신고·대여소 정보. 경보 규칙: 서로 다른 사람이 3분·300m 안 반납을 2번 이상 이어서 함.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("설정")
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("완료") { model.saveServer(); dismiss() } } }
        }
    }
}
