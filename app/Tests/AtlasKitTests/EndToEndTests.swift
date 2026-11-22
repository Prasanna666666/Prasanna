import CryptoKit
import XCTest
@testable import AtlasKit

/// The real Swift launcher and client against the real Python Core, as separate processes over a real Unix socket. Skipped unless `ATLAS_CI_PYTHON` names a Python with `atlas_core`
/// installed (the CI `macos` job sets it). The Core creates its keys in the real Keychain; they are removed afterwards.
final class EndToEndTests: XCTestCase {
    private let services = ["task-store", "designation-store", "documents-index", "mail-index", "model-record"].map { "atlas-\($0)" } + ["atlas-designation-anchor"]

    private func deleteKeychainItems() {
        for service in services {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/usr/bin/security")
            p.arguments = ["delete-generic-password", "-s", service]
            p.standardOutput = FileHandle.nullDevice
            p.standardError = FileHandle.nullDevice
            try? p.run()
            p.waitUntilExit()
        }
    }

    func testTheSwiftLauncherStartsARealCoreAndTheSwiftClientEnrolsActsAsOwnerAndSurvivesARestart() throws {
        guard let python = ProcessInfo.processInfo.environment["ATLAS_CI_PYTHON"] else { throw XCTSkip("ATLAS_CI_PYTHON is not set") }
        let base = URL(fileURLWithPath: "/tmp/atl" + UUID().uuidString.prefix(8).lowercased())  // a Unix socket path must stay under 104 bytes
        let dataDir = base.appendingPathComponent("core").path, socket = base.appendingPathComponent("run/core.sock").path
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        deleteKeychainItems()
        let launcher = CoreLauncher(executable: URL(fileURLWithPath: python), arguments: ["-m", "atlas_core.serve"])
        defer {
            launcher.stop()
            deleteKeychainItems()
            try? FileManager.default.removeItem(at: base)
        }

        try launcher.start(dataDir: dataDir, socket: socket)
        let code = try XCTUnwrap(launcher.bootstrapCode)
        XCTAssertGreaterThanOrEqual(code.count, 16)

        let signer = Curve25519.Signing.PrivateKey()
        let intruder = CoreClient(socketPath: socket, signer: Curve25519.Signing.PrivateKey(), clientID: "intruder-swift-ci01")
        XCTAssertThrowsError(try intruder.enrolSelf(bootstrapCode: "wrong-code-wrong-code-0000"), "a wrong code must not enrol")

        let owner = CoreClient(socketPath: socket, signer: signer, clientID: "owner-swift-ci-0001")
        try owner.enrolSelf(bootstrapCode: code)
        launcher.forgetCode()
        XCTAssertNil(launcher.bootstrapCode)
        XCTAssertEqual((try owner.consent()["grants"] as? [Any])?.count, 0)  // signed, owner-only, over the real socket
        XCTAssertEqual(try owner.mode(), "default")

        launcher.stop()  // shutdown, then a restart with the same data folder: the owner is still enrolled and needs no code
        try launcher.start(dataDir: dataDir, socket: socket)
        let again = CoreClient(socketPath: socket, signer: signer, clientID: "owner-swift-ci-0001")
        XCTAssertEqual((try again.consent()["grants"] as? [Any])?.count, 0)
        XCTAssertThrowsError(try intruder.enrolSelf(bootstrapCode: launcher.bootstrapCode), "even the new code cannot create a second owner")
    }
}
