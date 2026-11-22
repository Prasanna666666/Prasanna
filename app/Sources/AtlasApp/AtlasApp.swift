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
    @StateObject private var model = AppModel()
    var body: some Scene {
        WindowGroup("Atlas") {
            RootView(model: model).frame(minWidth: 520, minHeight: 420)
        }
        .commands {
            CommandMenu("Go") {
                ForEach(1...6, id: \.self) { number in
                    if let destination = Sidebar.destination(forShortcut: number, in: model.availability) {
                        Button(destination.title) { model.selection = destination }.keyboardShortcut(KeyEquivalent(Character("\(number)")), modifiers: .command)
                    }
                }
            }
        }
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

/// One finished or running exchange in the Ask Atlas conversation.
struct Turn: Identifiable {
    let id = UUID()
    let question: String
    var answer: AnswerView?
    var phase: TaskPhase?
    var failure: String?
    var taskID: String?
}

struct DeviceRow: Identifiable {
    let id: String
    let label: String
    let revoked: Bool
}

@MainActor
final class AppModel: ObservableObject {
    // Navigation and launch
    @Published var selection: Destination = .home
    @Published var launch: LaunchState = .startingCore
    @Published var needsGetStarted = true
    // Library
    @Published var library: LoadState<LibraryPage> = .idle
    @Published var libraryQuery = ""
    @Published var librarySort = LibrarySort.bestMatch
    @Published var libraryFilter: String?
    // Conversation
    @Published var question = ""
    @Published var turns: [Turn] = []
    @Published var busy = false
    @Published var failure: String?
    @Published var selectedCitation: CitationView?
    @Published var evidence: EvidenceState?
    // Activity and approvals
    @Published var activity: [ActivityItem] = []
    @Published var attention: [ActivityItem] = []
    @Published var approval: ApprovalFlow?
    private var approvalPayload: [String: Any] = [:]  // the exact payload the Core asked approval for: it is what runs, never a rebuilt copy
    // Settings
    @Published var grants: [[String: Any]] = []
    @Published var indexLine = ""
    @Published var research = false
    @Published var devices: [DeviceRow] = []

    private var gate = SubmissionGate()
    private var tracker = PhaseTracker()
    private var currentTaskID: String?
    private let client: CoreClient?
    private let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Atlas")
    private var socket: String { support.appendingPathComponent("run/core.sock").path }
    static let completedKey = "atlas.getStartedCompleted"
    static let selectionKey = "atlas.selection"

    init() {
        client = (try? KeyStore.identity()).map { CoreClient(socketPath: FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Atlas/run/core.sock").path, signer: $0.signer, clientID: $0.id) }
        selection = Sidebar.restored(UserDefaults.standard.string(forKey: Self.selectionKey), in: availability)
        Task { await startCoreThenRefresh() }
    }

    /// What the app can really show: the Library appears once something is enabled to search. No domain is listed that has no surface yet.
    var availability: Availability { Availability(library: !scope.isEmpty) }

    /// The source types the owner has enabled, in words and as Core names (what is in scope for a question).
    var scope: [String] { grants.compactMap { $0["source_type"] as? String } }
    var scopeLine: String {
        let names = scope.map { Catalogue.shared.sourceKinds[$0] ?? $0.capitalized }
        return names.isEmpty ? "No sources are enabled." : "Searching: " + names.joined(separator: ", ")
    }

    func select(_ destination: Destination) {
        selection = destination
        UserDefaults.standard.set(destination.restorationKey, forKey: Self.selectionKey)
    }

    // MARK: launch and consent

    func startCoreThenRefresh() async {
        launch = .startingCore
        let dataDir = support.appendingPathComponent("core").path, sock = socket
        do { try await Task.detached { try Launcher.shared.start(dataDir: dataDir, socket: sock) }.value } catch {
            if case .local(let text)? = error as? AtlasError { launch = LaunchState.from(launchError: text) } else { launch = .coreUnavailable(UnavailableReason.coreUnreachable.message) }
            return
        }
        launch = .ready
        await refreshConsent()
        await loadSettings()
    }

    func refreshConsent() async {
        guard let client else { return }
        do {
            let state = try await Task.detached { try client.consent() }.value
            let active = ((state["grants"] as? [[String: Any]]) ?? []).filter { ($0["revoked"] as? Bool) == false }
            grants = active
            needsGetStarted = GetStartedFlow.needsGetStarted(completedOnce: UserDefaults.standard.bool(forKey: Self.completedKey), activeGrants: active.count)
        } catch AtlasError.core(let code) where code == "unauthenticated" {
            // First run: the Core does not know this client yet. Enrol it as the owner client (accepted once, over the owner-only socket), then ask again.
            do { try await Task.detached { try client.enrolSelf(bootstrapCode: Launcher.bootstrapCode) }.value; Launcher.shared.forgetCode(); await refreshConsent() } catch { failure = (error as? AtlasError)?.message }
        } catch { launch = .coreUnavailable(UnavailableReason.coreUnreachable.message) }
    }

    /// The owner's first-run choice. Nothing chosen means no request to the Core and so no grant; the choice (even an empty one) is remembered so Get Started is not shown again.
    func complete(_ choice: GetStartedChoice) async {
        failure = nil
        if let sources = GetStartedFlow.request(for: choice) {
            guard let client else { return }
            do { _ = try await Task.detached { try client.enable(sources) }.value } catch { failure = (error as? AtlasError)?.message; return }
        }
        UserDefaults.standard.set(true, forKey: Self.completedKey)
        needsGetStarted = false
        await refreshConsent()
        await loadSettings()
    }

    // MARK: library

    func searchLibrary() async {
        let text = libraryQuery.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let client, !text.isEmpty else { library = .idle; return }
        guard !scope.isEmpty else { library = .denied("Atlas is not allowed to search that. Turn on a source in Settings."); return }
        library = .loading
        libraryFilter = nil
        let sources = scope
        do {
            let response = try await Task.detached { try client.librarySearch(text, scope: sources) }.value
            library = LibraryOutcome.from(response)
        } catch { library = .failed((error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")) }
    }

    // MARK: conversation

    func ask() async {
        let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let client, !text.isEmpty, !scope.isEmpty, gate.begin() else { return }  // a second submission while one runs is ignored here, not just by the button
        busy = true; failure = nil; selectedCitation = nil; evidence = nil
        tracker = PhaseTracker()
        turns.append(Turn(question: text, answer: nil, phase: .received, failure: nil, taskID: nil))
        let index = turns.count - 1
        let sources = scope
        defer { busy = false; gate.end() }
        do {
            let id = try await Task.detached { try client.ask(question: text, scope: sources) }.value
            currentTaskID = id
            turns[index].taskID = id
            question = ""
            while true {
                let state = try await Task.detached { try client.state(id) }.value
                if let phase = tracker.update(coreState: state) { turns[index].phase = phase }
                if TaskPhase.from(coreState: state).isTerminal || TaskPhase.from(coreState: state) == .unknown { break }
                try await Task.sleep(nanoseconds: 300_000_000)
            }
            let raw = try await Task.detached { try client.answer(id) }.value
            turns[index].answer = AnswerView(raw)
            record(task: text, phase: turns[index].phase ?? .completed, id: id)
        } catch {
            let message = (error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")
            turns[index].failure = message
            turns[index].phase = .failed
            failure = message  // the question stays in the composer so nothing typed is lost
            record(task: text, phase: .failed, id: turns[index].id.uuidString)
        }
    }

    private func record(task text: String, phase: TaskPhase, id: String) {
        activity.append(ActivityItem(id: id, kind: .task, title: text, detail: phase.label, date: Date(), needsAttention: phase == .failed || phase == .completedWithLimitations))
    }

    func cancel() async {
        guard let client, let id = currentTaskID else { return }
        _ = try? await Task.detached { try client.cancel(id) }.value
    }

    func showEvidence(turn: Turn, citation: CitationView) async {
        guard let client, let id = turn.taskID else { return }
        selectedCitation = citation
        evidence = nil
        do {
            let text = try await Task.detached { try client.passage(id, index: citation.id) }.value
            evidence = EvidenceState.from(coreCode: nil, text: text)
        } catch AtlasError.core(let code) { evidence = EvidenceState.from(coreCode: code, text: nil) } catch { evidence = .unsupportedLocator }
    }

    func closeEvidence() { selectedCitation = nil; evidence = nil }

    // MARK: approvals (exact action, exact payload; the owner decides)

    /// Propose a typed action as the owner. If it needs approval the sheet shows the exact payload; nothing runs until the owner approves.
    func propose(action: String, payload: [String: Any]) async {
        guard let client else { return }
        do {
            let outcome = try await Task.detached { try client.act(action, payload: payload) }.value
            guard (outcome["status"] as? String) == "needs_approval", let approvalID = outcome["approval_id"] as? String, let category = outcome["category"] as? Int,
                  let exact = outcome["exact_payload"] as? [String: Any], let summary = ApprovalDescriber.describe(approvalID: approvalID, action: action, payload: exact, category: category) else {
                if (outcome["status"] as? String) == "done" { activity.append(ActivityItem(id: UUID().uuidString, kind: .action, title: action, detail: "Done", date: Date())) }
                return
            }
            approvalPayload = exact
            approval = ApprovalFlow(summary: summary, expiresAt: Date().addingTimeInterval(540))
            activity.append(ActivityItem(id: "approval-" + approvalID, kind: .decision, title: summary.title, detail: "Waiting for your approval", date: Date(), needsAttention: true))
        } catch { failure = (error as? AtlasError)?.message }
    }

    func approveCurrent() async {
        guard let client, var flow = approval, flow.approved(now: Date()) else { return }
        approval = flow
        let payload = approvalPayload
        let approvalID = flow.summary.approvalID, action = flow.summary.action
        do {
            let granted = try await Task.detached { try client.approve(approvalID: approvalID) }.value
            guard granted else { flow.finished(success: false, message: "The approval could not be recorded."); approval = flow; return }
            let outcome = try await Task.detached { try client.act(action, payload: payload, approvalID: approvalID) }.value
            let done = (outcome["status"] as? String) == "done"
            flow.finished(success: done, message: "That could not be done. Nothing was changed.")
            approval = flow
        } catch { flow.finished(success: false, message: (error as? AtlasError)?.message ?? "That could not be done."); approval = flow }
    }

    func declineCurrent() { if var flow = approval { flow.declined(); approval = flow } }
    func dismissApproval() { approval = nil }

    // MARK: settings

    func loadSettings() async {
        guard let client else { return }
        do {
            let state = try await Task.detached { try client.consent() }.value
            grants = (state["grants"] as? [[String: Any]] ?? []).filter { ($0["revoked"] as? Bool) == false }
            let status = try await Task.detached { try client.indexStatus() }.value
            research = (try await Task.detached { try client.mode() }.value) == "research"
            indexLine = "Indexed \(status["indexed"] as? Int ?? 0) of \(status["total"] as? Int ?? 0), \(status["state"] as? String ?? "")."
            await loadDevices()
            await loadAttention()
        } catch { failure = (error as? AtlasError)?.message }
    }

    /// What needs the owner's attention, from the Core (computed by code from the owner's own records). If the Core has none or cannot say, the group stays hidden.
    func loadAttention() async {
        guard let client else { return }
        let raw = (try? await Task.detached { try client.attention() }.value) ?? []
        attention = raw.compactMap { ActivityItem.fromAttention($0, now: Date()) }
    }

    func loadDevices() async {
        guard let client else { return }
        let rows = (try? await Task.detached { try client.devices() }.value) ?? []
        devices = rows.map { DeviceRow(id: $0["device_id"] as? String ?? "", label: ($0["label"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "Unnamed device", revoked: !($0["revoked_at"] is NSNull) && $0["revoked_at"] != nil) }
    }

    func revoke(device: DeviceRow) async {
        guard let client else { return }
        do { _ = try await Task.detached { try client.revokeDevice(device.id) }.value; await loadDevices() } catch { failure = (error as? AtlasError)?.message }
    }

    /// Research mode lets Atlas use the larger, slower model for harder questions. Only the owner chooses it; it switches off again when Atlas restarts.
    func setResearch(_ on: Bool) async {
        guard let client else { return }
        do { research = (try await Task.detached { try client.setMode(on ? "research" : "default") }.value) == "research" } catch { failure = (error as? AtlasError)?.message }
    }

    func withdraw(_ grantID: String) async {
        guard let client else { return }
        do { _ = try await Task.detached { try client.withdraw(grantID: grantID) }.value; await refreshConsent(); await loadSettings() } catch { failure = (error as? AtlasError)?.message }
    }
}
