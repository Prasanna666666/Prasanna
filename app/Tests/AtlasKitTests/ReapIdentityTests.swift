import XCTest
@testable import AtlasKit

/// The launcher never signals a process on the strength of a pid or a name alone: the process must have the recorded start time and a command line that ends with exactly this socket and data folder, and that is checked
/// again before the forceful signal.
final class ReapIdentityTests: XCTestCase {
    private var children: [Process] = []
    private var base: URL!

    override func setUpWithError() throws {
        base = URL(fileURLWithPath: "/tmp/atl" + UUID().uuidString.prefix(8).lowercased())
        try FileManager.default.createDirectory(at: base.appendingPathComponent("run"), withIntermediateDirectories: true)
    }

    override func tearDown() {
        children.forEach { if $0.isRunning { $0.terminate() } }
        children.forEach { $0.waitUntilExit() }
        try? FileManager.default.removeItem(at: base)
    }

    private var socket: String { base.appendingPathComponent("run/core.sock").path }
    private var dataDir: String { base.appendingPathComponent("core").path }
    private var pidFile: URL { base.appendingPathComponent("run/core.pid") }

    /// A process whose command line looks like a Core's, so it can be told apart only by what the launcher checks.
    private func lookalike(dataDir: String, socket: String) throws -> Process {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = ["python3", "-c", "import time; time.sleep(120)", "atlas_core.serve", "--data-dir", dataDir, "--socket", socket]
        p.standardError = FileHandle.nullDevice
        try p.run()
        children.append(p)
        Thread.sleep(forTimeInterval: 0.5)
        return p
    }

    private func record(for p: Process, started: String? = nil, socket: String? = nil, dataDir: String? = nil) throws {
        let now = try XCTUnwrap(CoreLauncher.identify(p.processIdentifier))
        let value = CoreLauncher.Recorded(pid: p.processIdentifier, started: started ?? now.started, socket: socket ?? self.socket, dataDir: dataDir ?? self.dataDir)
        try JSONEncoder().encode(value).write(to: pidFile)
    }

    private func reap() throws { try CoreLauncher(executable: URL(fileURLWithPath: "/usr/bin/false"), arguments: []).reapLeftovers(socket: socket) }

    func testTheCoreThisAppStartedForThisSocketAndFolderIsStopped() throws {
        let p = try lookalike(dataDir: dataDir, socket: socket)
        try record(for: p)
        try reap()
        p.waitUntilExit()
        XCTAssertFalse(p.isRunning)
    }

    func testAReusedPidOrAnotherCoreOrABrokenRecordIsNeverSignalled() throws {
        let other = try lookalike(dataDir: base.appendingPathComponent("elsewhere").path, socket: socket)
        try record(for: other)  // the pid and start are right, but it was started for a different data folder
        try reap()
        XCTAssertTrue(other.isRunning, "another Core with a different data folder must be left alone")

        let mine = try lookalike(dataDir: dataDir, socket: socket)
        try record(for: mine, started: "Mon Jan  1 00:00:00 1990")  // the pid was reused: the process started at another time
        try reap()
        XCTAssertTrue(mine.isRunning, "a process with another start time is not the recorded Core")

        try record(for: mine, socket: base.appendingPathComponent("run/other.sock").path)
        try reap()
        XCTAssertTrue(mine.isRunning, "a record for another socket does not authorise anything here")

        for junk in ["not json", String(mine.processIdentifier), "{\"pid\": 1}", ""] {
            try junk.write(to: pidFile, atomically: true, encoding: .utf8)  // malformed, an old plain pid, or incomplete
            try reap()
            XCTAssertTrue(mine.isRunning, "an untrusted pid file (\(junk.prefix(8))) kills nothing")
        }
    }

    func testAProcessThatChangesBetweenTheGentleAndTheForcefulSignalIsNeverKilled() throws {
        let p = try lookalike(dataDir: dataDir, socket: socket)
        try record(for: p)
        let real = CoreLauncher.identify
        var calls = 0
        var sent: [Int32] = []
        CoreLauncher.identify = { pid in
            calls += 1
            guard let now = real(pid) else { return nil }
            return calls <= 1 ? now : (started: "Tue Feb  2 02:02:02 2002", command: now.command)  // after the first check the process is no longer the recorded one
        }
        CoreLauncher.sendSignal = { _, signal in sent.append(signal); return 0 }  // record, do not really signal
        CoreLauncher.termGrace = 0.3
        defer { CoreLauncher.identify = real; CoreLauncher.sendSignal = { Darwin.kill($0, $1) }; CoreLauncher.termGrace = 10 }
        try reap()
        XCTAssertEqual(sent, [SIGTERM], "the gentle signal was sent once and the forceful one never, because the identity no longer matched")
        XCTAssertTrue(p.isRunning)
    }
}
