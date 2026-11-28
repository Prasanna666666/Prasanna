import CryptoKit
import XCTest
@testable import AtlasKit

/// The real Swift launcher and client against the real Python Core, as separate processes over a real Unix socket. Skipped unless `ATLAS_CI_PYTHON` names a Python with `atlas_core`
/// installed (the CI `macos` job sets it). The Core creates its keys in the real Keychain; they are removed afterwards.
final class EndToEndTests: XCTestCase {
    private let services = ["task-store", "designation-store", "documents-index", "mail-index", "edits-store", "model-record"].map { "atlas-\($0)" } + ["atlas-designation-anchor", "atlas-installation", "atlas-restore-journal"]

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
        let environment = ProcessInfo.processInfo.environment
        if environment["CI"] != nil { XCTAssertNotNil(environment["ATLAS_CI_PYTHON"], "on CI this test must run, not be skipped") }  // GitHub Actions sets CI
        guard let python = environment["ATLAS_CI_PYTHON"] else { throw XCTSkip("ATLAS_CI_PYTHON is not set") }
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

    // MARK: lifecycle

    private func python() throws -> String {
        let environment = ProcessInfo.processInfo.environment
        if environment["CI"] != nil { XCTAssertNotNil(environment["ATLAS_CI_PYTHON"], "on CI this test must run, not be skipped") }
        return try XCTUnwrap(environment["ATLAS_CI_PYTHON"], "ATLAS_CI_PYTHON is not set")
    }

    private func workspace() throws -> (base: URL, dataDir: String, socket: String) {
        let base = URL(fileURLWithPath: "/tmp/atl" + UUID().uuidString.prefix(8).lowercased())
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        return (base, base.appendingPathComponent("core").path, base.appendingPathComponent("run/core.sock").path)
    }

    private func alive(_ pid: Int32) -> Bool { kill(pid, 0) == 0 }

    func testStopTerminatesWaitsForAndReapsTheCoreAndStartIsIdempotent() throws {
        guard ProcessInfo.processInfo.environment["ATLAS_CI_PYTHON"] != nil || ProcessInfo.processInfo.environment["CI"] != nil else { throw XCTSkip("ATLAS_CI_PYTHON is not set") }
        let py = try python(), w = try workspace()
        deleteKeychainItems()
        let launcher = CoreLauncher(executable: URL(fileURLWithPath: py), arguments: ["-m", "atlas_core.serve"])
        defer { launcher.stop(); deleteKeychainItems(); try? FileManager.default.removeItem(at: w.base) }
        try launcher.start(dataDir: w.dataDir, socket: w.socket)
        let pid = try XCTUnwrap(launcher.processID)
        try launcher.start(dataDir: w.dataDir, socket: w.socket)  // a second start while running must not start a second Core
        XCTAssertEqual(launcher.processID, pid)
        launcher.stop()
        XCTAssertFalse(launcher.isRunning)
        XCTAssertFalse(alive(pid), "stop must leave no process behind")
    }

    func testARelaunchedAppReapsTheCoreItsPredecessorLeftBehindAndStartsOneCleanCore() throws {
        guard ProcessInfo.processInfo.environment["ATLAS_CI_PYTHON"] != nil || ProcessInfo.processInfo.environment["CI"] != nil else { throw XCTSkip("ATLAS_CI_PYTHON is not set") }
        let py = try python(), w = try workspace()
        deleteKeychainItems()
        let first = CoreLauncher(executable: URL(fileURLWithPath: py), arguments: ["-m", "atlas_core.serve"])
        let second = CoreLauncher(executable: URL(fileURLWithPath: py), arguments: ["-m", "atlas_core.serve"])
        defer { first.stop(); second.stop(); deleteKeychainItems(); try? FileManager.default.removeItem(at: w.base) }
        do { try first.start(dataDir: w.dataDir, socket: w.socket) } catch { XCTFail("first.start threw: \(error)"); throw error }
        let oldPid = try XCTUnwrap(first.processID)
        // The app "crashed" without stopping its Core: a new app instance (a new launcher object) starts against the same folder and socket.
        do { try second.start(dataDir: w.dataDir, socket: w.socket) } catch { XCTFail("second.start threw: \(error)"); throw error }
        let newPid = try XCTUnwrap(second.processID)
        XCTAssertNotEqual(oldPid, newPid)
        XCTAssertFalse(alive(oldPid) && first.isRunning, "the Core left behind must have been stopped")
        let signer = Curve25519.Signing.PrivateKey()
        let owner = CoreClient(socketPath: w.socket, signer: signer, clientID: "owner-swift-ci-0002")
        do { try owner.enrolSelf(bootstrapCode: second.bootstrapCode) } catch { XCTFail("enrolSelf threw: \(error)"); throw error }
        //  // the one Core on that socket is the new one and answers
        XCTAssertEqual((try owner.consent()["grants"] as? [Any])?.count, 0)
    }

    func testAStaleSocketFileAndAStalePidFileDoNotPreventStartingAndAnUnrelatedPidIsNeverKilled() throws {
        guard ProcessInfo.processInfo.environment["ATLAS_CI_PYTHON"] != nil || ProcessInfo.processInfo.environment["CI"] != nil else { throw XCTSkip("ATLAS_CI_PYTHON is not set") }
        let py = try python(), w = try workspace()
        deleteKeychainItems()
        try FileManager.default.createDirectory(atPath: (w.socket as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: w.socket, contents: Data("stale".utf8))  // a leftover file where the socket goes
        let unrelated = Process()  // an unrelated process whose pid is written in the pid file: it must survive
        unrelated.executableURL = URL(fileURLWithPath: "/bin/sleep")
        unrelated.arguments = ["30"]
        try unrelated.run()
        try String(unrelated.processIdentifier).write(toFile: (w.socket as NSString).deletingLastPathComponent + "/core.pid", atomically: true, encoding: .utf8)
        let launcher = CoreLauncher(executable: URL(fileURLWithPath: py), arguments: ["-m", "atlas_core.serve"])
        defer { launcher.stop(); unrelated.terminate(); unrelated.waitUntilExit(); deleteKeychainItems(); try? FileManager.default.removeItem(at: w.base) }
        try launcher.start(dataDir: w.dataDir, socket: w.socket)
        XCTAssertTrue(launcher.isRunning)
        XCTAssertTrue(unrelated.isRunning, "a pid that is not this Core must never be terminated")
    }

    /// A listener that really answers on the socket path (bound and listening, in this process).
    private func listen(on path: String) throws -> Int32 {
        let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        XCTAssertGreaterThanOrEqual(fd, 0)
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8CString)
        withUnsafeMutableBytes(of: &address.sun_path) { buffer in for (i, byte) in bytes.enumerated() { buffer[i] = UInt8(bitPattern: byte) } }
        let length = socklen_t(MemoryLayout<sockaddr_un>.size)
        let bound = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, length) } }
        XCTAssertEqual(bound, 0)
        XCTAssertEqual(Darwin.listen(fd, 16), 0)
        return fd
    }

    func testALiveListenerIsNeverUnlinkedWhateverThePidFileSaysAndStartingFailsSafely() throws {
        let w = try workspace()
        try FileManager.default.createDirectory(atPath: (w.socket as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: w.base) }
        let pidFile = (w.socket as NSString).deletingLastPathComponent + "/core.pid"
        let unrelated = Process()  // a live process that is NOT this Core
        unrelated.executableURL = URL(fileURLWithPath: "/bin/sleep")
        unrelated.arguments = ["30"]
        try unrelated.run()
        defer { unrelated.terminate(); unrelated.waitUntilExit() }
        let cases: [(String, String?)] = [("absent", nil), ("malformed", "not-a-pid"), ("stale", "999999"), ("unmatched", String(unrelated.processIdentifier))]
        for (name, content) in cases {
            try? FileManager.default.removeItem(atPath: w.socket)
            try? FileManager.default.removeItem(atPath: pidFile)
            if let content = content { try content.write(toFile: pidFile, atomically: true, encoding: .utf8) }
            let listener = try listen(on: w.socket)
            defer { close(listener) }
            let launcher = CoreLauncher(executable: URL(fileURLWithPath: "/usr/bin/false"), arguments: [])
            XCTAssertThrowsError(try launcher.start(dataDir: w.dataDir, socket: w.socket), "pid file \(name)")
            XCTAssertTrue(FileManager.default.fileExists(atPath: w.socket), "the live socket must still exist (pid file \(name))")
            XCTAssertTrue(CoreLauncher.isAnswering(socket: w.socket), "the listener must still answer (pid file \(name))")
            XCTAssertTrue(unrelated.isRunning, "an unrelated process is never terminated (pid file \(name))")
            XCTAssertFalse(launcher.isRunning)
        }
    }

    func testAnUnansweredSocketFileIsRemovedAndAnAnsweredOneIsReported() throws {
        let w = try workspace()
        try FileManager.default.createDirectory(atPath: (w.socket as NSString).deletingLastPathComponent, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: w.base) }
        FileManager.default.createFile(atPath: w.socket, contents: Data("stale".utf8))
        XCTAssertFalse(CoreLauncher.isAnswering(socket: w.socket))
        let launcher = CoreLauncher(executable: URL(fileURLWithPath: "/usr/bin/false"), arguments: [])
        try launcher.reapLeftovers(socket: w.socket)
        XCTAssertFalse(FileManager.default.fileExists(atPath: w.socket))
        let listener = try listen(on: w.socket)
        defer { close(listener) }
        XCTAssertTrue(CoreLauncher.isAnswering(socket: w.socket))
    }

    func testACoreThatExitsBecauseTheKeychainIsLockedIsReportedAsNeedingOwnerSignIn() throws {
        let w = try workspace()
        defer { try? FileManager.default.removeItem(at: w.base) }
        let script = w.base.appendingPathComponent("locked.sh")  // stands in for a Core that exits with the needs-sign-in status
        try "#!/bin/sh\nexit 6\n".write(to: script, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: script.path)
        let launcher = CoreLauncher(executable: script, arguments: [])
        XCTAssertThrowsError(try launcher.start(dataDir: w.dataDir, socket: w.socket, timeoutSeconds: 10)) { error in
            XCTAssertTrue("\(error)".contains("Mac needs owner sign-in"), "\(error)")
        }
        XCTAssertFalse(launcher.isRunning)
    }
}
