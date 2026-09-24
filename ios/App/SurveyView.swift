import SwiftUI
import PhotosUI
import HeotgeoleumCore

/// 현장 조사: 대여소의 자전거를 한 대씩 보고 상태·메모·사진을 남긴다. 서버에 못 보내면 폰에 모았다가 다음에.
struct SurveyView: View {
    @Environment(AppModel.self) private var model
    @State private var filter = ""
    @State private var stationID = ""
    @State private var bike = ""
    @State private var note = ""
    @State private var photo: Data?
    @State private var pickerItem: PhotosPickerItem?
    @State private var camera = false
    @State private var count = UserDefaults.standard.integer(forKey: "survey_n")

    var body: some View {
        NavigationStack {
            Form {
                Section("대여소") {
                    Button { Task { if await model.locate() != nil { stationID = candidates.first?.id ?? stationID } } } label: {
                        Label("가까운 대여소 찾기", systemImage: "location")
                    }
                    TextField("이름으로 찾기 (예: 망원역)", text: $filter).accessibilityLabel("대여소 이름으로 찾기")
                    Picker("대여소", selection: $stationID) {
                        ForEach(candidates) { s in Text(label(s)).tag(s.id) }
                    }
                }
                Section("자전거") {
                    TextField("SPB-00000", text: $bike)
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                        .font(.title3.monospaced())
                        .accessibilityLabel("조사한 자전거 번호")
                    TextField("메모(선택): 바람 빠짐, 체인 빠짐…", text: $note)
                    HStack {
                        PhotosPicker(selection: $pickerItem, matching: .images) { Label("사진 고르기", systemImage: "photo") }
                        if UIImagePickerController.isSourceTypeAvailable(.camera) {
                            Button { camera = true } label: { Label("찍기", systemImage: "camera") }
                        }
                        Spacer()
                        if let photo, let img = UIImage(data: photo) {
                            Image(uiImage: img).resizable().scaledToFill().frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: 8))
                            Button(role: .destructive) { self.photo = nil } label: { Image(systemName: "xmark.circle") }.accessibilityLabel("사진 빼기")
                        }
                    }
                    .buttonStyle(.borderless)
                }
                Section {
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                        ForEach(ServerClient.surveyStatuses, id: \.self) { st in
                            Button { Task { await save(st) } } label: { Text(st).frame(maxWidth: .infinity, minHeight: 40) }
                                .buttonStyle(.bordered)
                                .tint(st == "멀쩡함" ? Palette.good : Palette.red)
                        }
                    }
                } header: {
                    Text("상태 (누르면 저장)")
                } footer: {
                    Text("이 기기로 \(count)대 기록\(model.queued > 0 ? " · 서버에 못 보낸 \(model.queued)건은 폰에 보관 중" : "")\n번호판·사람 얼굴이 사진에 안 나오게 해 주세요. 절차: docs/field_protocol.md")
                }
            }
            .navigationTitle("현장 조사")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
            .onChange(of: pickerItem) {
                Task {
                    if let d = try? await pickerItem?.loadTransferable(type: Data.self) { photo = PhotoShrink.jpeg(d) }
                    pickerItem = nil
                }
            }
            .sheet(isPresented: $camera) {
                CameraPicker { img in photo = img.flatMap { PhotoShrink.jpeg($0) } }.ignoresSafeArea()
            }
            .onAppear { if stationID.isEmpty { stationID = candidates.first?.id ?? "" } }
        }
    }

    /// 위치를 알면 가까운 30곳, 아니면 이름순 (이름으로 거름)
    private var candidates: [Station] {
        var list = Array((model.store?.stations ?? [:]).values)
        if !filter.isEmpty { list = list.filter { $0.name.contains(filter) } }
        if let here = model.here {
            return Array(list.sorted { Geo.meters(here, $0.point) < Geo.meters(here, $1.point) }.prefix(30))
        }
        return Array(list.sorted { $0.name.compare($1.name, locale: Locale(identifier: "ko_KR")) == .orderedAscending }.prefix(300))
    }
    private func label(_ s: Station) -> String {
        guard let here = model.here else { return s.name }
        return "\(s.name) · \(Int(Geo.meters(here, s.point).rounded()))m"
    }

    private func save(_ status: String) async {
        guard let id = BikeID.normalize(bike) else { model.show("자전거 번호(SPB-00000)를 먼저 넣어 주세요."); return }
        guard !stationID.isEmpty else { model.show("대여소를 골라 주세요."); return }
        await model.survey(SurveyRecord(station: stationID, bike: id, status: status, note: note, lat: model.here?.lat, lon: model.here?.lon, photoJPEG: photo))
        count += 1
        UserDefaults.standard.set(count, forKey: "survey_n")
        bike = ""; note = ""; photo = nil
    }
}

enum PhotoShrink {
    /// 긴 변 1280px JPEG(품질 0.7)로 줄이기 — 몇 MB 원본 → 약 150KB (웹앱과 같은 기준)
    static func jpeg(_ data: Data) -> Data? { UIImage(data: data).flatMap { jpeg($0) } }
    static func jpeg(_ img: UIImage, max: CGFloat = 1280) -> Data? {
        let k = min(1, max / Swift.max(img.size.width, img.size.height))
        let size = CGSize(width: (img.size.width * k).rounded(), height: (img.size.height * k).rounded())
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        let out = UIGraphicsImageRenderer(size: size, format: format).image { _ in img.draw(in: CGRect(origin: .zero, size: size)) }
        return out.jpegData(compressionQuality: 0.7)
    }
}

/// 카메라로 바로 찍기
struct CameraPicker: UIViewControllerRepresentable {
    let done: (UIImage?) -> Void
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let p = UIImagePickerController()
        p.sourceType = .camera
        p.delegate = context.coordinator
        return p
    }
    func updateUIViewController(_ vc: UIImagePickerController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(done: done) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let done: (UIImage?) -> Void
        init(done: @escaping (UIImage?) -> Void) { self.done = done }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            done(info[.originalImage] as? UIImage)
            picker.dismiss(animated: true)
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            done(nil)
            picker.dismiss(animated: true)
        }
    }
}
