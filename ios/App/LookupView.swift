import SwiftUI
import AVFoundation
import HeotgeoleumCore

struct LookupView: View {
    @Environment(AppModel.self) private var model
    @State private var input = ""
    @State private var result: Result?
    @State private var scanning = false

    enum Result: Equatable { case suspect(SuspectBike), clean(String), notABike(String) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    Text("따릉이를 빌리기 전에 자전거 번호(예: SPB-69683)를 넣거나 QR 을 비추세요.")
                        .font(.subheadline).foregroundStyle(.secondary)
                    HStack {
                        TextField("SPB-00000", text: $input)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .font(.title3.monospaced())
                            .textFieldStyle(.roundedBorder)
                            .onSubmit { lookup(input) }
                            .accessibilityLabel("자전거 번호")
                        Button("조회") { lookup(input) }.buttonStyle(.borderedProminent)
                    }
                    Button { scanning = true } label: {
                        Label("QR 로 찍기", systemImage: "qrcode.viewfinder").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    resultView
                }
                .padding(16)
            }
            .navigationTitle("자전거 조회")
            .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
            .fullScreenCover(isPresented: $scanning) {
                QRScanner { code in
                    scanning = false
                    input = code
                    lookup(code)
                } cancel: { scanning = false }
                .ignoresSafeArea()
            }
        }
    }

    func lookup(_ raw: String) {
        guard let id = BikeID.normalize(raw) else { result = .notABike(String(raw.prefix(60))); return }
        if let hit = model.morning?.bikes.first(where: { $0.bike == id }) { result = .suspect(hit) } else { result = .clean(id) }
    }

    @ViewBuilder private var resultView: some View {
        switch result {
        case .suspect(let b):
            VStack(alignment: .leading, spacing: 10) {
                Label("\(b.bike) 는 피하세요", systemImage: "exclamationmark.triangle.fill").font(.title3.bold()).foregroundStyle(Palette.red)
                Text("어제까지 **서로 다른 \(b.chain)명**이 이 자전거를 빌리자마자 반납했어요 (마지막 \(b.lastDud), \(b.stationName)).")
                Text("이런 자전거는 다음 사람도 \(b.isRed ? "약 70%" : "약 35~55%")가 바로 반납했어요. 옆 자전거를 고르세요.")
                VerdictButtons(bike: b.bike)
            }
            .padding(14)
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.red))
        case .clean(let id):
            Label("\(id) — 어제까지 기록에 헛걸음 연쇄가 없어요.", systemImage: "checkmark.circle.fill")
                .foregroundStyle(Palette.good).padding(14)
                .overlay(RoundedRectangle(cornerRadius: 12).stroke(Palette.good))
        case .notABike(let raw):
            // QR 속 글자는 Text 로만 보여 준다(해석하지 않음)
            Text("따릉이 번호(SPB-00000)를 못 찾았어요: ") + Text(verbatim: raw).font(.body.monospaced())
        case nil:
            EmptyView()
        }
    }
}

/// 구조대 판정 네 가지 (조회·구조대 탭이 같이 씀)
struct VerdictButtons: View {
    @Environment(AppModel.self) private var model
    let bike: String
    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
            ForEach([("체인·기어", false), ("타이어", false), ("안장·핸들", false), ("멀쩡해요", true)], id: \.0) { label, fine in
                Button {
                    Task { await model.rescue(bike, fine ? "멀쩡함" : label) }
                } label: {
                    Text(label).frame(maxWidth: .infinity, minHeight: 36)
                }
                .buttonStyle(.bordered)
                .tint(fine ? Palette.good : Palette.red)
            }
        }
    }
}

/// QR 카메라 — AVFoundation 으로 QR 을 읽어 글자를 돌려준다
struct QRScanner: UIViewControllerRepresentable {
    let found: (String) -> Void
    let cancel: () -> Void

    func makeUIViewController(context: Context) -> ScannerController {
        let c = ScannerController()
        c.found = found
        c.cancel = cancel
        return c
    }
    func updateUIViewController(_ vc: ScannerController, context: Context) {}
}

final class ScannerController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var found: ((String) -> Void)?
    var cancel: (() -> Void)?
    private let session = AVCaptureSession()
    private var done = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        let close = UIButton(type: .system, primaryAction: UIAction(title: "닫기") { [weak self] _ in self?.cancel?() })
        close.tintColor = .white
        close.titleLabel?.font = .preferredFont(forTextStyle: .headline)
        close.translatesAutoresizingMaskIntoConstraints = false
        guard let device = AVCaptureDevice.default(for: .video), let input = try? AVCaptureDeviceInput(device: device), session.canAddInput(input) else {
            let label = UILabel()
            label.text = "카메라를 쓸 수 없어요. 번호를 직접 넣어 주세요."
            label.textColor = .white
            label.numberOfLines = 0
            label.frame = view.bounds.insetBy(dx: 24, dy: 200)
            view.addSubview(label)
            addClose(close)
            return
        }
        session.addInput(input)
        let output = AVCaptureMetadataOutput()
        if session.canAddOutput(output) {
            session.addOutput(output)
            output.setMetadataObjectsDelegate(self, queue: .main)
            output.metadataObjectTypes = [.qr]
        }
        let preview = AVCaptureVideoPreviewLayer(session: session)
        preview.videoGravity = .resizeAspectFill
        preview.frame = view.layer.bounds
        view.layer.addSublayer(preview)
        addClose(close)
        DispatchQueue.global(qos: .userInitiated).async { [session] in session.startRunning() }
    }

    private func addClose(_ b: UIButton) {
        view.addSubview(b)
        NSLayoutConstraint.activate([b.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12),
                                     b.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -20)])
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        view.layer.sublayers?.compactMap { $0 as? AVCaptureVideoPreviewLayer }.forEach { $0.frame = view.layer.bounds }
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        if session.isRunning { DispatchQueue.global().async { [session] in session.stopRunning() } }
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput objects: [AVMetadataObject], from connection: AVCaptureConnection) {
        guard !done, let code = (objects.first as? AVMetadataMachineReadableCodeObject)?.stringValue else { return }
        done = true
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        found?(code)
    }
}
