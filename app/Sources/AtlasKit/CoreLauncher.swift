import Foundation
import Security

/// Starts the Core as a child process of the app and hands it a one-time bootstrap code over the child's standard input: a pipe only the app and that child hold. The code is never on a
/// command line, in the environment, in a file or in a log, and lives in this object's memory until `forgetCode()`. Mirrors `core/src/atlas_core/launcher.py` (the verified Python
/// counterpart, tested with a real child process). UNBUILT: never compiled or run.
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

    public func start(dataDir: String, socket: String, timeoutSeconds: Double = 60) throws {
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
    }

    /// Call once the owner is enrolled: the code is spent and must not linger.
    public func forgetCode() { bootstrapCode = nil }
    public func stop() { process?.terminate(); process = nil }
}
