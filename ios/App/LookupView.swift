import SwiftUI
import AVFoundation
import HeotgeoleumCore

struct LookupView: View {
    @Environment(AppModel.self) private var model
    @State private var input = ""
    @State private var result: Result?
    @State private var scanning = false
    @FocusState private var typing: Bool

    enum Result: Equatable { case suspect(SuspectBike), clean(String), notABike(String) }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("타기 전에\n자전거 번호를 확인해 보세요")
                        .font(.system(size: 26, weight: .bold)).foregroundStyle(Palette.ink)
                        .padding(.horizontal, 4).padding(.top, 8)
                    VStack(spacing: 10) {
                        TextField("SPB-00000", text: $input)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .font(.system(size: 22, weight: .semibold).monospacedDigit())
                            .foregroundStyle(Palette.ink)
                            .focused($typing)
                            .submitLabel(.search)
                            .onSubmit { lookup(input) }
                            .padding(.horizontal, 18).padding(.vertical, 16)
                            .background(Palette.fill, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .accessibilityLabel("자전거 번호")
                        Button("조회하기") { lookup(input) }.buttonStyle(PrimaryButtonStyle())
                        Button { scanning = true } label: { Label("QR 로 찍기", systemImage: "qrcode.viewfinder") }
                            .buttonStyle(SoftButtonStyle(tint: Palette.ink))
                    }
                    .card(padding: 16)
                    resultView
                }
                .padding(.horizontal, 16).padding(.bottom, 32)
            }
            .screenBackground()
            .scrollDismissesKeyboard(.interactively)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .topBarTrailing) { SettingsButton() } }
            .onAppear {   // 실행 인자 `-lookup SPB-69683` (화면 사진·시연용)
                if result == nil, let q = UserDefaults.standard.string(forKey: "lookup") { input = q; lookup(q) }
                takeQuery()
            }
            .onChange(of: model.lookupQuery) { takeQuery() }
            .onChange(of: model.day) { if result != nil, !input.isEmpty { lookup(input) } }   // 실시간 목록이 늦게 들어와 기준이 바뀌면 다시
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

    private func takeQuery() {   // 홈의 의심 자전거 한 줄을 눌렀을 때
        guard let q = model.lookupQuery else { return }
        model.lookupQuery = nil
        input = q
        lookup(q)
    }

    func lookup(_ raw: String) {
        typing = false
        guard let id = BikeID.normalize(raw) else { result = .notABike(String(raw.prefix(60))); return }
        withAnimation(.snappy) {
            if let hit = model.morning?.bikes.first(where: { $0.bike == id }) { result = .suspect(hit) } else { result = .clean(id) }
        }
    }

    private var until: String { model.day == AppModel.liveDay ? "최근" : model.isPastData ? "\(AppModel.koDay(model.day)) 아침 목록에서" : "어제까지" }

    /// 지난 자료로 본 결과일 때 — 지금 이 자전거 상태는 모른다고 분명히
    @ViewBuilder private var pastNote: some View {
        if model.isPastData {
            Text("\(AppModel.koDay(model.day)) 자료예요. 지금 상태는 홈에서 '실시간' 을 고르면 볼 수 있어요\(model.live == nil ? " (지금은 실시간 목록을 못 받았어요)" : "").")
                .font(.footnote).foregroundStyle(Palette.sub)
        }
    }

    /// 설명 한 줄: 왼쪽 이름, 오른쪽 값
    private func fact(_ k: String, _ v: String, _ color: Color = Palette.ink) -> some View {
        HStack { Text(k).foregroundStyle(Palette.sub); Spacer(); Text(v).fontWeight(.semibold).foregroundStyle(color).multilineTextAlignment(.trailing) }
            .font(.subheadline)
    }

    @ViewBuilder private var resultView: some View {
        switch result {
        case .suspect(let b):
            VStack(alignment: .leading, spacing: 16) {
                Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 36)).foregroundStyle(Palette.red)
                    .symbolEffect(.bounce, value: b.bike)
                (Text(b.bike).monospacedDigit() + Text("는\n타지 마세요"))
                    .font(.system(size: 26, weight: .bold)).foregroundStyle(Palette.ink)
                md("\(until) **서로 다른 \(b.chain)명**이 빌리자마자 반납했어요. 옆 자전거를 골라 주세요.")
                    .font(.body).foregroundStyle(Palette.body)
                VStack(spacing: 10) {
                    fact(b.pNext == nil ? "다음 사람도 반납할 확률" : "다음 사람도 반납할 확률 (모델)", b.nextRiderText, Palette.red)
                    fact("평소 자전거", "2.5%")
                    fact("마지막 반납", b.lastDud)
                    fact("대여소", b.stationName)
                }
                .padding(16)
                .background(Palette.fill, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                Text("가까이 있다면, 어디가 이상했나요?").font(.subheadline.weight(.semibold)).foregroundStyle(Palette.sub).padding(.top, 4)
                VerdictButtons(bike: b.bike)
                pastNote
            }
            .card(padding: 22, tint: Palette.redSoft)
            .sensoryFeedback(.warning, trigger: b.bike)
            .transition(.opacity.combined(with: .move(edge: .bottom)))
        case .clean(let id) where model.isPastData:
            // 지난 자료에 없다는 건 '괜찮다' 가 아니다 — 초록 체크 대신 모른다고
            VStack(alignment: .leading, spacing: 12) {
                Image(systemName: "questionmark.circle.fill").font(.system(size: 36)).foregroundStyle(Palette.sub)
                (Text(id).monospacedDigit() + Text("는\n\(AppModel.koDay(model.day)) 자료에 없어요")).font(.system(size: 24, weight: .bold)).foregroundStyle(Palette.ink)
                pastNote
            }
            .card(padding: 22)
        case .clean(let id):
            VStack(alignment: .leading, spacing: 12) {
                Image(systemName: "checkmark.circle.fill").font(.system(size: 36)).foregroundStyle(Palette.good)
                    .symbolEffect(.bounce, value: id)
                (Text(id).monospacedDigit() + Text("는\n타도 괜찮아요")).font(.system(size: 26, weight: .bold)).foregroundStyle(Palette.ink)
                Text("\(until) 기록에 빌리자마자 반납한 연쇄가 없어요.").font(.body).foregroundStyle(Palette.body)
                if let note = model.morning?.feed?.note { Label(note, systemImage: "hourglass").font(.footnote).foregroundStyle(Palette.yellowText) }
            }
            .card(padding: 22, tint: Palette.goodSoft)
            .sensoryFeedback(.success, trigger: id)
            .transition(.opacity.combined(with: .move(edge: .bottom)))
        case .notABike(let raw):
            // QR 속 글자는 Text 로만 보여 준다(해석하지 않음)
            VStack(alignment: .leading, spacing: 8) {
                Text("따릉이 번호를 못 찾았어요").font(.headline).foregroundStyle(Palette.ink)
                (Text("SPB-00000 모양으로 넣어 주세요. 읽은 글자: ") + Text(verbatim: raw).font(.body.monospaced())).font(.subheadline).foregroundStyle(Palette.sub)
            }
            .card()
        case nil:
            EmptyView()
        }
    }
}

/// 판정 네 가지 (조회·확인 탭이 같이 씀) — 회색 단추, 멀쩡하면 초록 글자
struct VerdictButtons: View {
    @Environment(AppModel.self) private var model
    @State private var tapped = 0
    let bike: String
    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)], spacing: 8) {
            ForEach([("체인·기어", false), ("타이어", false), ("안장·핸들", false), ("멀쩡해요", true)], id: \.0) { label, fine in
                Button {
                    tapped += 1
                    Task { await model.rescue(bike, fine ? "멀쩡함" : label) }
                } label: {
                    Text(label)
                }
                .buttonStyle(SoftButtonStyle(tint: fine ? Palette.good : Palette.ink))
            }
        }
        .sensoryFeedback(.success, trigger: tapped)
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
