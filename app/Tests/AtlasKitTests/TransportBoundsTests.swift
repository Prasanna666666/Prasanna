import XCTest
@testable import AtlasKit

/// The Unix-socket transport cannot be ended by its peer (no SIGPIPE), never waits forever, and never reads an unbounded reply (review findings ATLAS-TRANSPORT-098 and ATLAS-TRANSPORT-099).
final class TransportBoundsTests: XCTestCase {
    private var server: Process?
    private var base: URL!

    override func setUpWithError() throws {
        base = URL(fileURLWithPath: "/tmp/atl" + UUID().uuidString.prefix(8).lowercased())
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
    }

    override func tearDown() {
        if let server, server.isRunning { server.terminate() }
        server?.waitUntilExit()
        try? FileManager.default.removeItem(at: base)
    }

    private var socketPath: String { base.appendingPathComponent("s.sock").path }

    /// A throwaway server: `mode` is `close` (accept, then close without reading) or `flood` (read the request, then send bytes without end).
    private func serve(_ mode: String) throws {
        let script = """
        import socket, sys, os
        path, mode = sys.argv[1], sys.argv[2]
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(path); s.listen(1)
        c, _ = s.accept()
        if mode == "close":
            c.close()
        else:
            c.recv(65536)
            chunk = b"x" * 65536
            try:
                while True: c.sendall(chunk)
            except OSError:
                pass
        """
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        p.arguments = ["python3", "-c", script, socketPath, mode]
        p.standardError = FileHandle.nullDevice
        try p.run()
        server = p
        for _ in 0..<100 where !FileManager.default.fileExists(atPath: socketPath) { Thread.sleep(forTimeInterval: 0.05) }
        XCTAssertTrue(FileManager.default.fileExists(atPath: socketPath))
    }

    func testAPeerThatClosesWhileTheRequestIsBeingWrittenIsAnErrorNotACrash() throws {
        try serve("close")
        let big = Data(repeating: 0x41, count: 4_000_000)
        XCTAssertThrowsError(try UnixHTTP(path: socketPath).send(method: "POST", target: "/v1/x", headers: [:], body: big))
    }

    func testAnEndlessReplyIsStoppedAtTheCapAndIsAnError() throws {
        try serve("flood")
        XCTAssertThrowsError(try UnixHTTP(path: socketPath).send(method: "GET", target: "/v1/x", headers: [:], body: Data())) { error in
            XCTAssertTrue("\(error)".contains("response too large") || "\(error)".contains("response"), "\(error)")
        }
    }
}
