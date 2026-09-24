import SwiftUI

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        @Bindable var model = model
        NavigationStack {
            Form {
                Section {
                    TextField("http://내맥이름.local:8765", text: $model.serverURL)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                } header: {
                    Text("맥 서버 주소 (선택)")
                } footer: {
                    Text("같은 와이파이의 맥에서 python server/app.py 를 켜 두면 구조대 확인·현장 조사가 맥으로 모입니다. 비워 두면 이 폰에만 남아요. 앱이라서 https 가 아니어도 됩니다.")
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
