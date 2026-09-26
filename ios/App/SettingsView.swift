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
                    Text("맥 서버 주소 (선택)")
                    Button(checking ? "확인하는 중…" : "연결 확인") {
                        Task { checking = true; model.saveServer(); await model.refreshLive(); checking = false }
                    }
                    .disabled(checking || model.serverURL.isEmpty)
                    if let s = model.serverStatus { Text(s).font(.footnote) }
                } footer: {
                    Text("맥의 '시스템 설정 → 일반 → 공유' 맨 아래 이름 뒤에 .local:8765 를 붙여 넣으세요 (예: http://내맥이름.local:8765). 폰과 맥이 같은 와이파이여야 하고, 맥이 켜져 있어야 '지금' 목록이 떠요. 연결 안 돼도 구조대 확인·현장 조사는 폰에 보관했다가 나중에 보냅니다.")
                }
                Section("자료") {
                    LabeledContent("아침 목록", value: "\(model.store?.days.count ?? 0)일 (\(model.store?.days.first ?? "") ~ \(model.store?.days.last ?? ""))")
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
