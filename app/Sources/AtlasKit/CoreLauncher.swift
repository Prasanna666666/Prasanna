#if os(macOS)
import Foundation
import Security

/// Starts the Core as a child process of the app and hands it a one-time bootstrap code over the child's standard input: a pipe only the app and that child hold. The code is never on a
/// command line, in the environment, in a file or in a log, and lives in this object's memory until `forgetCode()`. Mirrors `core/src/atlas_core/launcher.py` (the verified Python
/// counterpart, tested with a real child process). Exercised against the real Core by `EndToEndTests` on the macOS CI runner.
///
/// Lifecycle: `start` is idempotent (a second call while the child runs does nothing) and first reaps a Core a previous app instance left behind (recorded in a pid file next to the socket, and
/// only if that pid still runs this Core); `stop` asks the child to terminate, waits, kills it if it does not, and reaps it. The Core also stops by itself when its parent is gone.
public final class CoreLauncher {
    /// The Core's exit status when the Keychain is locked (`serve.EXIT_NEEDS_SIGNIN`).
    public static let needsOwnerSignInStatus: Int32 = 6
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

    /// What the launcher writes next to the socket, and checks before it ever signals a process: the pid, WHEN that process started, and the exact socket and data folder it was started for.
    /// A pid alone is not an identity (pids are reused); an older plain-number file is not trusted at all.
    struct Recorded: Codable, Equatable {
        let pid: Int32
        let started: String
        let socket: String
        let dataDir: String
    }

    /// The start time and the full command line of a process, or nil if there is no such process. A seam so tests can show a process changing underneath the launcher.
    nonisolated(unsafe) static var identify: (Int32) -> (started: String, command: String)? = { pid in
        func ps(_ field: String) -> String? {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/bin/ps")
            p.arguments = ["-p", String(pid), "-o", field + "="]
            let out = Pipe()
            p.standardOutput = out
            p.standardError = FileHandle.nullDevice
            do { try p.run() } catch { return nil }
            let data = out.fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            let text = String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
            return text.isEmpty ? nil : text
        }
        guard let started = ps("lstart"), let command = ps("command") else { return nil }
        return (started, command)
    }

    nonisolated(unsafe) static var sendSignal: (Int32, Int32) -> Int32 = { Darwin.kill($0, $1) }
    nonisolated(unsafe) static var termGrace: Double = 10

    /// This process is the Core this app started for this socket and data folder: same start time as recorded, and the command line ends with exactly `--data-dir <folder> --socket <socket>`.
    static func verified(_ record: Recorded, socket: String) -> Bool {
        guard record.socket == socket, !record.started.isEmpty, let now = identify(record.pid), now.started == record.started else { return false }
        return now.command.contains("atlas_core.serve") && now.command.hasSuffix("--data-dir \(record.dataDir) --socket \(socket)")
    }

    static func isAnswering(socket path: String) -> Bool {
        let fd = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { return false }
        defer { close(fd) }
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        let bytes = Array(path.utf8CString)
        guard bytes.count <= MemoryLayout.size(ofValue: address.sun_path) else { return false }
        withUnsafeMutableBytes(of: &address.sun_path) { buffer in for (i, byte) in bytes.enumerated() { buffer[i] = UInt8(bitPattern: byte) } }
        let length = socklen_t(MemoryLayout<sockaddr_un>.size)
        return withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.connect(fd, $0, length) == 0 } }
    }

    /// Stop a Core a previous app instance left running (only a process that is really this Core, never an unrelated one that reused the pid). The socket file is removed ONLY once nothing answers on it:
    /// if a listener still answers after that (the pid file was missing, malformed, stale or unmatched, so no Core was identified and stopped), the socket and the pid file are left untouched and
    /// starting fails safely, because removing a live socket would strand the running Core while a second one is refused by the data-folder lock.
    func reapLeftovers(socket: String) throws {
        let file = pidFile(socket)
        let recorded: Recorded? = (try? Data(contentsOf: file)).flatMap { try? JSONDecoder().decode(Recorded.self, from: $0) }
        if let record = recorded, Self.isRunning(record.pid), Self.verified(record, socket: socket) {
            _ = Self.sendSignal(record.pid, SIGTERM)
            var waited = 0.0
            while Self.isRunning(record.pid), waited < Self.termGrace { Thread.sleep(forTimeInterval: 0.1); waited += 0.1 }
            if Self.isRunning(record.pid), Self.verified(record, socket: socket) { _ = Self.sendSignal(record.pid, SIGKILL); Thread.sleep(forTimeInterval: 0.2) }  // identity is checked again: a process that changed meanwhile is never killed
        }
        if Self.isAnswering(socket: socket) { throw AtlasError.local("a Core is already answering on this socket and could not be identified as this app's own; it was left alone") }
        if recorded.map({ !Self.isRunning($0.pid) }) ?? true { try? FileManager.default.removeItem(at: file) }  // a pid file for a process that no longer runs
        try? FileManager.default.removeItem(atPath: socket)  // a socket file nothing listens on
    }

    public func start(dataDir: String, socket: String, timeoutSeconds: Double = 60) throws {
        if let running = process, running.isRunning { return }  // already started: starting twice must not start a second Core on the same folder
        try reapLeftovers(socket: socket)
        let code = try Self.makeCode()
        let child = Process()
        child.executableURL = executable
        child.arguments = arguments + ["--data-dir", dataDir, "--socket", socket]
        let input = Pipe(), output = Pipe()
        child.standardInput = input
        child.standardOutput = output
        child.standardError = FileHandle.nullDevice
        try child.run()
        let record = Recorded(pid: child.processIdentifier, started: Self.identify(child.processIdentifier)?.started ?? "", socket: socket, dataDir: dataDir)
        try? JSONEncoder().encode(record).write(to: pidFile(socket), options: .atomic)
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
            let deadline = Date().addingTimeInterval(10)
            while child.isRunning, Date() < deadline { Thread.sleep(forTimeInterval: 0.05) }
            if child.isRunning { kill(child.processIdentifier, SIGKILL) }
            child.waitUntilExit()  // a Core that did not become ready is stopped and reaped, never left behind
            // exit code 6: the Keychain would not give the store keys, which is the normal state of a Mac that restarted and has not been signed in to (FileVault stays on; no auto-login)
            throw AtlasError.local(child.terminationStatus == CoreLauncher.needsOwnerSignInStatus ? "Mac needs owner sign-in" : "the Core did not start")
        }
        process = child
        bootstrapCode = code
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
#endif
