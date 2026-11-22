import Foundation
import Security

/// Starts the Core as a child process of the app and hands it a one-time bootstrap code over the child's standard input: a pipe only the app and that child hold. The code is never on a
/// command line, in the environment, in a file or in a log, and lives in this object's memory until `forgetCode()`. Mirrors `core/src/atlas_core/launcher.py` (the verified Python
/// counterpart, tested with a real child process). Exercised against the real Core by `EndToEndTests` on the macOS CI runner.
///
/// Lifecycle: `start` is idempotent (a second call while the child runs does nothing) and first reaps a Core a previous app instance left behind (recorded in a pid file next to the socket, and
/// only if that pid still runs this Core); `stop` asks the child to terminate, waits, kills it if it does not, and reaps it. The Core also stops by itself when its parent is gone.
public final class CoreLauncher {
    public private(set) var bootstrapCode: String?
    private var process: Process?
    private let executable: URL
    private let arguments: [String]

    /// `executable` and `arguments` start `python -m atlas_core.serve` (or the packaged equivalent); packaging the Core into the app is not built.
    public init(executable: URL, arguments: [String]) { self.executable = executable; self.arguments = arguments }

    /// A random code of 32 characters from the alphabet the Core accepts (`[A-Za-z0-9_-]{16,64}`).
    static func makeCode() throws -> String {
        var bytes = [UInt8](repeating: 0, count: 24)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw AtlasError.local("no random code") }
        return Data(bytes).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }

    /// Where the running Core's pid is recorded, next to its socket, so a relaunched app can find and stop a Core its predecessor left behind.
    private func pidFile(_ socket: String) -> URL { URL(fileURLWithPath: socket).deletingLastPathComponent().appendingPathComponent("core.pid") }

    private static func isRunning(_ pid: Int32) -> Bool { kill(pid, 0) == 0 || errno == EPERM }

    private static func command(of pid: Int32) -> String {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/ps")
        p.arguments = ["-p", String(pid), "-o", "command="]
        let out = Pipe()
        p.standardOutput = out
        p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { return "" }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return String(decoding: data, as: UTF8.self)
    }

    /// Stop a Core a previous app instance left running (only a process that is really this Core, never an unrelated one that reused the pid), and remove a stale socket.
    func reapLeftovers(socket: String) {
        let file = pidFile(socket)
        if let text = try? String(contentsOf: file, encoding: .utf8), let pid = Int32(text.trimmingCharacters(in: .whitespacesAndNewlines)), Self.isRunning(pid),
           Self.command(of: pid).contains("atlas_core.serve") {
            kill(pid, SIGTERM)
            var waited = 0.0
            while Self.isRunning(pid), waited < 10 { Thread.sleep(forTimeInterval: 0.1); waited += 0.1 }
            if Self.isRunning(pid) { kill(pid, SIGKILL); Thread.sleep(forTimeInterval: 0.2) }
        }
        try? FileManager.default.removeItem(at: file)
        try? FileManager.default.removeItem(atPath: socket)  // a socket file nothing listens on
    }

    public func start(dataDir: String, socket: String, timeoutSeconds: Double = 60) throws {
        if let running = process, running.isRunning { return }  // already started: starting twice must not start a second Core on the same folder
        reapLeftovers(socket: socket)
        let code = try Self.makeCode()
        let child = Process()
        child.executableURL = executable
        child.arguments = arguments + ["--data-dir", dataDir, "--socket", socket]
        let input = Pipe(), output = Pipe()
        child.standardInput = input
        child.standardOutput = output
        child.standardError = FileHandle.nullDevice
        try child.run()
        input.fileHandleForWriting.write(Data((code + "\n").utf8))
        try input.fileHandleForWriting.close()
        let ready = DispatchSemaphore(value: 0)
        var seen = Data()
        DispatchQueue.global().async {
            while !seen.contains(Data("READY".utf8)) {
                let block = output.fileHandleForReading.availableData
                if block.isEmpty { break }
                seen.append(block)
            }
            ready.signal()
        }
        guard ready.wait(timeout: .now() + timeoutSeconds) == .success, seen.contains(Data("READY".utf8)) else {
            child.terminate()
            throw AtlasError.local("the Core did not start")
        }
        process = child
        bootstrapCode = code
        try? String(child.processIdentifier).write(to: pidFile(socket), atomically: true, encoding: .utf8)
        pidPath = pidFile(socket)
    }

    /// Call once the owner is enrolled: the code is spent and must not linger.
    public func forgetCode() { bootstrapCode = nil }
    private var pidPath: URL?

    /// Ask the Core to stop (it shuts down cleanly on SIGTERM), wait for it, kill it if it does not, and reap it so no process or zombie is left.
    public func stop() {
        guard let child = process else { return }
        if child.isRunning {
            child.terminate()
            let deadline = Date().addingTimeInterval(15)
            while child.isRunning, Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if child.isRunning { kill(child.processIdentifier, SIGKILL) }
        }
        child.waitUntilExit()
        process = nil
        if let path = pidPath { try? FileManager.default.removeItem(at: path) }
        pidPath = nil
    }

    public var isRunning: Bool { process?.isRunning ?? false }
    public var processID: Int32? { process.map { $0.processIdentifier } }
}
