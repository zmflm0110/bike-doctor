// swift-tools-version:5.9
// 헛걸음 제로 아이폰 앱의 엔진 — 화면(SwiftUI)과 떼어 둔 부분. 리눅스에서도 빌드·검사된다(docker swift), 앱(ios/App)은 Xcode 에서.
import PackageDescription

let package = Package(
    name: "HeotgeoleumCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "HeotgeoleumCore", targets: ["HeotgeoleumCore"])],
    targets: [
        .target(name: "HeotgeoleumCore"),
        .testTarget(name: "HeotgeoleumCoreTests", dependencies: ["HeotgeoleumCore"], resources: [.copy("Fixtures")]),
    ]
)
