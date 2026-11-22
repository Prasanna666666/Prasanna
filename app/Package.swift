// swift-tools-version: 5.9
// UNBUILT: written on Linux where no Swift toolchain exists. Build and test on a Mac: `swift build && swift test` (see README.md).
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
