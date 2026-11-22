// swift-tools-version: 5.9
// Built and tested on a macOS CI runner (`swift build && swift test`, see README.md); never launched.
import PackageDescription

let package = Package(
    name: "Atlas",
    platforms: [.macOS(.v14)],
    products: [.library(name: "AtlasKit", targets: ["AtlasKit"]), .executable(name: "AtlasApp", targets: ["AtlasApp"])],
    targets: [
        .target(name: "AtlasKit", resources: [.copy("ux_catalogue.json")]),
        .executableTarget(name: "AtlasApp", dependencies: ["AtlasKit"]),
        .testTarget(name: "AtlasKitTests", dependencies: ["AtlasKit"]),
    ]
)
