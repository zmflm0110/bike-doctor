import SwiftUI
import UIKit
import VisionKit
import HeotgeoleumCore

/// 카메라로 자전거 번호 읽기 — 애플 기기 안 글자 인식(VisionKit, 인터넷 없이). 대여소에서 여러 대를 한꺼번에 비추면
/// 번호마다 상자가 붙는다: 의심 자전거는 빨강(그 자전거의 AI 확률), 목록에 없으면 초록. QR 도 같이 읽는다. 상자를 누르면 그 자전거 조회.
/// 지원 기기(A12 이상, iOS 16+)가 아니면 LookupView 가 예전 QR 읽기(QRScanner)를 쓴다.
struct LiveScanner: UIViewControllerRepresentable {
    let suspects: [String: SuspectBike]
    let picked: (String) -> Void
    let cancel: () -> Void

    static var usable: Bool { DataScannerViewController.isSupported && DataScannerViewController.isAvailable }

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let vc = DataScannerViewController(recognizedDataTypes: [.text(), .barcode(symbologies: [.qr])], qualityLevel: .balanced,
                                           recognizesMultipleItems: true, isHighFrameRateTrackingEnabled: true, isPinchToZoomEnabled: true,
                                           isGuidanceEnabled: false, isHighlightingEnabled: false)
        vc.delegate = context.coordinator
        context.coordinator.vc = vc
        let close = UIButton(type: .system, primaryAction: UIAction(title: "닫기") { _ in cancel() })
        close.tintColor = .white
        close.titleLabel?.font = .preferredFont(forTextStyle: .headline)
        close.translatesAutoresizingMaskIntoConstraints = false
        let hint = UILabel()
        hint.text = "자전거 번호판이나 QR 을 비추세요 — 빨강은 피하세요"
        hint.textColor = .white
        hint.font = .preferredFont(forTextStyle: .subheadline)
        hint.textAlignment = .center
        hint.numberOfLines = 0
        hint.backgroundColor = UIColor.black.withAlphaComponent(0.45)
        hint.layer.cornerRadius = 12
        hint.clipsToBounds = true
        hint.translatesAutoresizingMaskIntoConstraints = false
        vc.view.addSubview(close)
        vc.view.addSubview(hint)
        NSLayoutConstraint.activate([
            close.topAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.topAnchor, constant: 12),
            close.trailingAnchor.constraint(equalTo: vc.view.trailingAnchor, constant: -20),
            hint.bottomAnchor.constraint(equalTo: vc.view.safeAreaLayoutGuide.bottomAnchor, constant: -24),
            hint.centerXAnchor.constraint(equalTo: vc.view.centerXAnchor),
            hint.widthAnchor.constraint(lessThanOrEqualTo: vc.view.widthAnchor, constant: -40),
            hint.heightAnchor.constraint(greaterThanOrEqualToConstant: 44),
        ])
        try? vc.startScanning()
        return vc
    }

    func updateUIViewController(_ vc: DataScannerViewController, context: Context) {}

    static func dismantleUIViewController(_ vc: DataScannerViewController, coordinator: Coordinator) { vc.stopScanning() }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let parent: LiveScanner
        weak var vc: DataScannerViewController?
        private var boxes: [RecognizedItem.ID: UILabel] = [:]
        private var warned: Set<String> = []

        init(_ parent: LiveScanner) { self.parent = parent }

        private func bikeID(_ item: RecognizedItem) -> String? {
            switch item {
            case .text(let t): return BikeID.fromScan(t.transcript)
            case .barcode(let b): return b.payloadStringValue.flatMap(BikeID.normalize)
            @unknown default: return nil
            }
        }

        private func draw(_ item: RecognizedItem) {
            guard let vc, let id = bikeID(item) else { boxes.removeValue(forKey: item.id)?.removeFromSuperview(); return }
            let b = item.bounds
            let xs = [b.topLeft.x, b.topRight.x, b.bottomLeft.x, b.bottomRight.x], ys = [b.topLeft.y, b.topRight.y, b.bottomLeft.y, b.bottomRight.y]
            let rect = CGRect(x: xs.min()!, y: ys.min()!, width: xs.max()! - xs.min()!, height: ys.max()! - ys.min()!).insetBy(dx: -8, dy: -8)
            let hit = parent.suspects[id]
            let box = boxes[item.id] ?? {
                let l = UILabel()
                l.textAlignment = .center
                l.numberOfLines = 2
                l.adjustsFontSizeToFitWidth = true
                l.minimumScaleFactor = 0.6
                l.layer.cornerRadius = 10
                l.layer.borderWidth = 3
                l.clipsToBounds = true
                vc.overlayContainerView.addSubview(l)
                boxes[item.id] = l
                return l
            }()
            let color: UIColor = hit == nil ? .systemGreen : .systemRed
            box.layer.borderColor = color.cgColor
            box.backgroundColor = color.withAlphaComponent(0.28)
            box.textColor = .white
            box.font = .systemFont(ofSize: 15, weight: .heavy)
            box.text = hit.map { "\(id)\n피하세요\($0.pNext.map { " · \($0)%" } ?? "")" } ?? "\(id)\n괜찮아요"
            box.frame = CGRect(x: rect.minX, y: rect.minY, width: max(rect.width, 120), height: max(rect.height, 52))
            if hit != nil, !warned.contains(id) {   // 처음 본 의심 자전거에 한 번 떨림
                warned.insert(id)
                UINotificationFeedbackGenerator().notificationOccurred(.warning)
            }
        }

        func dataScanner(_ s: DataScannerViewController, didAdd added: [RecognizedItem], allItems: [RecognizedItem]) { added.forEach(draw) }
        func dataScanner(_ s: DataScannerViewController, didUpdate updated: [RecognizedItem], allItems: [RecognizedItem]) { updated.forEach(draw) }
        func dataScanner(_ s: DataScannerViewController, didRemove removed: [RecognizedItem], allItems: [RecognizedItem]) {
            removed.forEach { boxes.removeValue(forKey: $0.id)?.removeFromSuperview() }
        }
        func dataScanner(_ s: DataScannerViewController, didTapOn item: RecognizedItem) {
            if let id = bikeID(item) { parent.picked(id) }
        }
    }
}
