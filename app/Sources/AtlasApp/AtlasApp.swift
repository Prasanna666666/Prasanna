import AtlasKit
import CryptoKit
import Security
import SwiftUI

/// The app owns the Core it starts: quitting the app (menu, window close, logout, shutdown) stops it, waits for it and reaps it, so no Core keeps processing sources after the UI is gone.
/// If the app crashes instead, the Core stops by itself (it watches its parent) and the next launch reaps anything left behind (`CoreLauncher.reapLeftovers`).
final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func applicationWillTerminate(_ notification: Notification) { Launcher.shared.stop() }
}

@main
struct AtlasApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate
    @StateObject private var model = ConversationModel()
    var body: some Scene {
        WindowGroup("Atlas") {
            if model.needsGetStarted { GetStartedView(model: model) } else { ConversationView(model: model) }
        }
        Settings { SettingsView(model: model) }
    }
}

/// The owner client's identity lives in the Keychain: a random client id and an Ed25519 key, both generated once on first run. The public key is enrolled with the Core as the owner
/// client by `CoreClient.enrolSelf()` the first time the Core says it does not know this client (see `ConversationModel.refreshConsent`).
enum KeyStore {
    private static func read(_ service: String) -> Data? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecReturnData as String: true]
        var item: CFTypeRef?
        return SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess ? item as? Data : nil
    }

    private static func write(_ service: String, _ data: Data) throws {
        let add: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecValueData as String: data,
                                  kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        guard SecItemAdd(add as CFDictionary, nil) == errSecSuccess else { throw AtlasError.local("keychain") }
    }

    static func identity() throws -> (id: String, signer: Curve25519.Signing.PrivateKey) {
        let signer: Curve25519.Signing.PrivateKey
        if let data = read("atlas-owner-client") { signer = try Curve25519.Signing.PrivateKey(rawRepresentation: data) } else {
            signer = Curve25519.Signing.PrivateKey(); try write("atlas-owner-client", signer.rawRepresentation)
        }
        if let data = read("atlas-owner-client-id"), let id = String(data: data, encoding: .utf8) { return (id, signer) }
        let id = "owner-" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(16)
        try write("atlas-owner-client-id", Data(id.utf8))
        return (id, signer)
    }
}

/// The app owns its Core: it starts it with `CoreLauncher`, which generates a one-time bootstrap code, hands it to the Core over the child's standard input and keeps it in memory
/// here. A Core started any other way has no code and refuses to start on a fresh data folder. Where the Core executable comes from (packaging) is NOT built: `coreExecutable` points
/// at a Python with the `atlas_core` package, for development.
enum Launcher {
    private static let home = FileManager.default.homeDirectoryForCurrentUser
    /// The folders the owner designates: Documents and Apple Mail's own folder (the Core only reads them once the owner enabled the source AND macOS lets it list them), and the
    /// installed public key that signed the model manifest (bundled with the app; where it lives is part of packaging, not built).
    /// The Python bundled inside the app (`scripts/package_mac.sh`), else the system one for development.
    private static let bundledPython = Bundle.main.resourceURL?.appendingPathComponent("python/bin/python3")
    static let shared = CoreLauncher(
        executable: bundledPython.flatMap { FileManager.default.isExecutableFile(atPath: $0.path) ? $0 : nil } ?? URL(fileURLWithPath: "/usr/bin/python3"),
        arguments: ["-m", "atlas_core.serve",
                    "--documents-source", "documents=" + home.appendingPathComponent("Documents").path,
                    "--mail-source", "mail=" + home.appendingPathComponent("Library/Mail").path,
                    "--manifest-pubkey", home.appendingPathComponent("Library/Application Support/Atlas/models/manifest.pub").path])
    static var bootstrapCode: String? { shared.bootstrapCode }
}

@MainActor
final class ConversationModel: ObservableObject {
    @Published var question = ""
    @Published var progress = ""
    @Published var answer: AnswerView?
    @Published var failure: String?
    @Published var busy = false
    @Published var needsGetStarted = true
    @Published var passage: String?
    private var taskID: String?
    private let client: CoreClient?
    private let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Atlas")
    private var socket: String { support.appendingPathComponent("run/core.sock").path }

    init() {
        let path = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Atlas/run/core.sock").path
        client = (try? KeyStore.identity()).map { CoreClient(socketPath: path, signer: $0.signer, clientID: $0.id) }
        Task { await startCoreThenRefresh() }
    }

    /// Start the Core (handing it the one-time code), then ask what is enabled; the first call enrols this app as the owner client.
    @Published var grants: [[String: Any]] = []
    @Published var indexLine = ""
    @Published var research = false

    /// What the owner enabled and how far indexing has got (counts only), for the settings screen.
    func loadSettings() async {
        guard let client else { return }
        do {
            let state = try await Task.detached { try client.consent() }.value
            grants = (state["grants"] as? [[String: Any]] ?? []).filter { ($0["revoked"] as? Bool) == false }
            let status = try await Task.detached { try client.indexStatus() }.value
            research = (try await Task.detached { try client.mode() }.value) == "research"
            indexLine = "Indexed \(status["indexed"] as? Int ?? 0) of \(status["total"] as? Int ?? 0), \(status["state"] as? String ?? "")."
        } catch { failure = (error as? AtlasError)?.message }
    }

    /// Research mode lets Atlas use the larger, slower model for harder questions. Only the owner chooses it; it switches off again when Atlas restarts.
    func setResearch(_ on: Bool) async {
        guard let client else { return }
        do { research = (try await Task.detached { try client.setMode(on ? "research" : "default") }.value) == "research" } catch { failure = (error as? AtlasError)?.message }
    }

    func withdraw(_ grantID: String) async {
        guard let client else { return }
        do { _ = try await Task.detached { try client.withdraw(grantID: grantID) }.value; await loadSettings(); await refreshConsent() } catch { failure = (error as? AtlasError)?.message }
    }

    func startCoreThenRefresh() async {
        let dataDir = support.appendingPathComponent("core").path, sock = socket
        do { try await Task.detached { try Launcher.shared.start(dataDir: dataDir, socket: sock) }.value } catch { failure = (error as? AtlasError)?.message; return }
        await refreshConsent()
    }

    func refreshConsent() async {
        guard let client else { return }
        do {
            let state = try await Task.detached { try client.consent() }.value
            let active = ((state["grants"] as? [[String: Any]]) ?? []).filter { ($0["revoked"] as? Bool) == false }.count
            needsGetStarted = GetStartedFlow.needsGetStarted(completedOnce: UserDefaults.standard.bool(forKey: Self.completedKey), activeGrants: active)
        } catch AtlasError.core(let code) where code == "unauthenticated" {
            // First run: the Core does not know this client yet. Enrol it as the owner client (accepted once, over the owner-only socket), then ask again.
            do { try await Task.detached { try client.enrolSelf(bootstrapCode: Launcher.bootstrapCode) }.value; Launcher.shared.forgetCode(); await refreshConsent() } catch { failure = (error as? AtlasError)?.message }
        } catch { failure = (error as? AtlasError)?.message }
    }

    static let completedKey = "atlas.getStartedCompleted"

    /// The owner's first-run choice. Nothing chosen means no request to the Core and so no grant; the choice (even an empty one) is remembered so Get Started is not shown again.
    func complete(_ choice: GetStartedChoice) async {
        failure = nil
        if let sources = GetStartedFlow.request(for: choice) {
            guard let client else { return }
            do { _ = try await Task.detached { try client.enable(sources) }.value } catch { failure = (error as? AtlasError)?.message; return }
        }
        UserDefaults.standard.set(true, forKey: Self.completedKey)
        needsGetStarted = false
    }

    func ask(scope: [String]) async {
        guard let client, !question.isEmpty else { return }
        busy = true; failure = nil; answer = nil; passage = nil
        defer { busy = false }
        let text = question
        do {
            let id = try await Task.detached { try client.ask(question: text, scope: scope) }.value
            taskID = id
            while true {
                let state = try await Task.detached { try client.state(id) }.value
                progress = Catalogue.shared.taskStates[state] ?? ""
                if ["completed", "partially_completed", "failed", "cancelled", "expired"].contains(state) { break }
                try await Task.sleep(nanoseconds: 300_000_000)
            }
            let raw = try await Task.detached { try client.answer(id) }.value
            answer = AnswerView(raw)
        } catch { failure = (error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error") }
    }

    func cancel() async {
        guard let client, let id = taskID else { return }
        _ = try? await Task.detached { try client.cancel(id) }.value
    }

    func showPassage(_ index: Int) async {
        guard let client, let id = taskID else { return }
        do { passage = try await Task.detached { try client.passage(id, index: index) }.value } catch { failure = (error as? AtlasError)?.message }
    }
}

struct GetStartedView: View {
    @ObservedObject var model: ConversationModel
    @State private var choice = GetStartedChoice()  // everything off: only a deliberate choice creates a grant
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Welcome to Atlas").font(.largeTitle)
            Text("Atlas answers from your own documents and mail, on this Mac. Nothing leaves your computer. Atlas reads nothing until you choose it here. You can change this at any time.")
            Toggle("My documents", isOn: $choice.documents)
            Toggle("My mail (message text only; attachments are not read)", isOn: $choice.mail)
            if let failure = model.failure { Text(failure).foregroundStyle(.red) }
            Button(choice.sources.isEmpty ? "Continue without enabling anything" : "Continue") { Task { await model.complete(choice) } }
                .buttonStyle(.borderedProminent)
        }.padding(32).frame(minWidth: 520)
    }
}

/// What Atlas may read, with a way to stop. Withdrawing takes effect at once and removes what Atlas derived from that source.
struct SettingsView: View {
    @ObservedObject var model: ConversationModel
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("What Atlas may read").font(.title2)
            if model.grants.isEmpty { Text("Nothing is enabled.") }
            ForEach(Array(model.grants.enumerated()), id: \.offset) { _, grant in
                HStack {
                    Text((grant["source_type"] as? String ?? "").capitalized)
                    Spacer()
                    Button("Stop reading this") { Task { await model.withdraw(grant["grant_id"] as? String ?? "") } }
                }
            }
            Toggle("Research mode (slower, for harder questions)", isOn: Binding(get: { model.research }, set: { value in Task { await model.setResearch(value) } }))
            Text(model.indexLine).font(.footnote).foregroundStyle(.secondary)
            if let failure = model.failure { Text(failure).foregroundStyle(.red) }
        }.padding(20).frame(minWidth: 420).task { await model.loadSettings() }
    }
}

struct ConversationView: View {
    @ObservedObject var model: ConversationModel
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                TextField("Ask about your documents or mail", text: $model.question).textFieldStyle(.roundedBorder).onSubmit { Task { await model.ask(scope: ["documents", "mail"]) } }
                Button("Ask") { Task { await model.ask(scope: ["documents", "mail"]) } }.disabled(model.busy)
                if model.busy { Button("Cancel") { Task { await model.cancel() } } }
            }
            if model.busy { ProgressView(model.progress) }
            if let failure = model.failure { Text(failure).foregroundStyle(.red).accessibilityLabel("Problem: \(failure)") }
            if let a = model.answer {
                ScrollView {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(a.text).textSelection(.enabled)
                        Text(a.trust).font(.callout).foregroundStyle(.secondary)
                        Text(a.modelLine).font(.footnote).foregroundStyle(.secondary)
                        if let coverage = a.coverageLine { Text(coverage).font(.footnote).foregroundStyle(.secondary) }
                        ForEach(a.notices, id: \.self) { Label($0, systemImage: "exclamationmark.triangle") }
                        ForEach(a.notSearched, id: \.self) { Label($0, systemImage: "nosign") }
                        ForEach(a.citations) { c in
                            VStack(alignment: .leading) {
                                Text(c.label).bold()
                                if let q = c.quote { Text("“\(q)”") }
                                Button(Catalogue.shared.actions["open_source"] ?? "Show the source passage") { Task { await model.showPassage(c.id) } }
                            }
                        }
                    }
                }
            }
            if let passage = model.passage { GroupBox("Source passage") { Text(passage).textSelection(.enabled) } }
        }.padding(20).frame(minWidth: 640, minHeight: 420)
    }
}
