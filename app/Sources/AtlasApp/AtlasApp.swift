import AtlasKit
import CryptoKit
import Security
import SwiftUI
import UserNotifications

/// The app owns the Core it starts: quitting the app (menu, window close, logout, shutdown) stops it, waits for it and reaps it, so no Core keeps processing sources after the UI is gone.
/// If the app crashes instead, the Core stops by itself (it watches its parent) and the next launch reaps anything left behind (`CoreLauncher.reapLeftovers`).
final class AppDelegate: NSObject, NSApplicationDelegate {
    /// Test-scoped appearance: only the UI tests set ATLAS_UI_TEST_APPEARANCE, so the accessibility audit can run in a known, verified
    /// Light or Dark appearance. Without it the app follows the system, as always.
    func applicationWillFinishLaunching(_ notification: Notification) {
        switch ProcessInfo.processInfo.environment["ATLAS_UI_TEST_APPEARANCE"] {
        case "Dark": NSApp.appearance = NSAppearance(named: .darkAqua)
        case "Light": NSApp.appearance = NSAppearance(named: .aqua)
        default: break
        }
    }

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
    /// A development and CI override: a Python with `atlas_core` installed, named by the environment of the person running the app. The packaged app never sets it.
    private static let developmentPython: URL? = ProcessInfo.processInfo.environment["ATLAS_CI_PYTHON"].flatMap { FileManager.default.isExecutableFile(atPath: $0) ? URL(fileURLWithPath: $0) : nil }
    private static let bundledPython = Bundle.main.resourceURL?.appendingPathComponent("python/bin/python3")
    private static let support = home.appendingPathComponent("Library/Application Support/Atlas")
    /// The update screen exists only when the release-signing public key is installed: without it the Core is not told about updates and the section stays hidden.
    /// The phone channel is off unless the owner saved a private address for it in Settings; the Core refuses anything that is not private again.
    private static var relayArguments: [String] {
        guard let saved = UserDefaults.standard.string(forKey: "atlas.relayBind"), let bind = RelayBind.parse(saved) else { return [] }
        return ["--relay-bind", bind]
    }

    private static var updateArguments: [String] {
        let key = support.appendingPathComponent("release.pub")
        return FileManager.default.fileExists(atPath: key.path) ? ["--update-root", support.appendingPathComponent("app").path, "--update-pubkey", key.path] : []
    }
    static let shared: CoreLauncher = {
        prepareBrowser()
        return CoreLauncher(
        executable: developmentPython ?? bundledPython.flatMap { FileManager.default.isExecutableFile(atPath: $0.path) ? $0 : nil } ?? URL(fileURLWithPath: "/usr/bin/python3"),
        arguments: ["-m", "atlas_core.serve",
                    "--documents-source", "documents=" + home.appendingPathComponent("Documents").path,
                    "--mail-source", "mail=" + home.appendingPathComponent("Library/Mail").path,
                    "--manifest-pubkey", support.appendingPathComponent("models/manifest.pub").path] + updateArguments + relayArguments)
    }()

    /// The browser for web reading travels inside the app when it was packaged with one; the Core's worker finds it through this variable. Nothing is downloaded at run time.
    private static func prepareBrowser() {
        guard let folder = Bundle.main.resourceURL?.appendingPathComponent("browsers"), FileManager.default.fileExists(atPath: folder.path) else { return }
        setenv("PLAYWRIGHT_BROWSERS_PATH", folder.path, 1)
    }
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
    // Finance and sources the owner could still turn on
    @Published var financeServed = false
    @Published var finance: LoadState<FinanceView> = .idle
    @Published var healthServed = false
    @Published var health: LoadState<HealthView> = .idle
    @Published var voiceState: VoiceState = .idle
    private(set) lazy var voice: VoiceSession = VoiceSession(input: SystemSpeech(), draft: { [unowned self] in self.question }, setDraft: { [unowned self] in self.question = $0 })
    @Published var webServed = false
    @Published var webHosts: LoadState<[String]> = .idle
    @Published var webPage: WebPageView?
    @Published var webMessage: String?
    @Published var connectionsServed = false
    @Published var connections: LoadState<[ConnectorView]> = .idle
    @Published var connectionMessage: String?
    @Published var reading = false
    private(set) lazy var aloud: AloudSession = AloudSession(speaker: SystemSpeaker())
    @Published var highlights: AnswerView?
    @Published var highlightsNote: String?
    @Published var review: LoadState<ReviewView> = .idle
    @Published var updates: LoadState<UpdateView> = .idle
    @Published var updateMessage: String?
    @Published var offeredSources: [String] = []
    // Own records (Calendar, Contacts, Notes)
    @Published var editsAvailable = false
    @Published var ownRecords: [OwnDomain: LoadState<[OwnRecord]>] = [:]
    @Published var undoLabel: String?
    @Published var undoFailure: String?
    private var undoActionID: String?
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
    @Published var notificationsOn = UserDefaults.standard.bool(forKey: AppModel.notifyKey)
    private var notified: Set<String> = []
    static let notifyKey = "atlas.notify"
    @Published var approval: ApprovalFlow?
    private var approvalPayload: [String: Any] = [:]  // the exact payload the Core asked approval for: it is what runs, never a rebuilt copy
    // Settings
    @Published var grants: [[String: Any]] = []
    @Published var indexLine = ""
    @Published var research = false
    @Published var devices: [DeviceRow] = []
    @Published var pairingInvite: String?
    @Published var pairingMessage: String?

    private var gate = SubmissionGate()
    private var tracker = PhaseTracker()
    private var submissionCancellation = SubmissionCancellation()
    private var client: CoreClient?
    private let support = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Atlas")
    private var socket: String { support.appendingPathComponent("run/core.sock").path }
    static let completedKey = "atlas.getStartedCompleted"
    static let selectionKey = "atlas.selection"

    init() {
        selection = Sidebar.restored(UserDefaults.standard.string(forKey: Self.selectionKey), in: availability)
        Task { await retryLaunch() }
    }

    /// Opens the owner's identity in the Keychain, then starts the Core. Without an identity the Core is not started, onboarding cannot complete and no composer is shown; "Try again" comes back here.
    func retryLaunch() async {
        let resolved = LaunchState.resolveIdentity { try KeyStore.identity() }
        client = resolved.identity.map { CoreClient(socketPath: socket, signer: $0.signer, clientID: $0.id) }
        if let blocked = resolved.state {
            launch = blocked
            return
        }
        await startCoreThenRefresh()
    }

    /// What the app can really show: the Library appears once something is enabled to search. No domain is listed that has no surface yet.
    var availability: Availability { Availability(library: !scope.isEmpty, lifeAreas: (editsAvailable ? OwnDomain.allCases.map { $0.title } : []) + (financeServed ? [SourceNames.title("finance")] : []) + (healthServed ? [SourceNames.title("health")] : []) + (connectionsServed ? ["Connections"] : []) + (webServed ? ["Web"] : [])) }

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

    // MARK: finance and turning sources on

    func loadFinance() async {
        guard let client else { return }
        finance = .loading
        do {
            let response = try await Task.detached { try client.financeSummary() }.value
            financeServed = true
            finance = FinanceOutcome.from(response)
        } catch AtlasError.core(let code) where code == "not_found" {
            financeServed = false
            finance = .unavailable(.notAvailableYet)
        } catch { finance = .failed((error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")) }
    }

    func loadHealth() async {
        guard let client else { return }
        health = .loading
        do {
            let response = try await Task.detached { try client.healthSummary() }.value
            healthServed = true
            health = HealthOutcome.from(response)
        } catch AtlasError.core(let code) where code == "not_found" {
            healthServed = false
            health = .unavailable(.notAvailableYet)
        } catch { health = .failed((error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")) }
    }

    func loadWeb() async {
        guard let client else { return }
        do {
            webHosts = WebOutcome.hosts(try await Task.detached { try client.webHosts() }.value)
            webServed = true
        } catch AtlasError.core(let code) where code == "not_found" {
            webServed = false
            webHosts = .idle
        } catch { webHosts = .failed((error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")) }
    }

    func addWebHost(_ host: String) async {
        guard let client else { return }
        webMessage = nil
        let name = host.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        do { _ = try await Task.detached { try client.addWebHost(name) }.value; await loadWeb() } catch AtlasError.core(let code) { webMessage = WebOutcome.message(forCoreCode: code) } catch { webMessage = Catalogue.shared.error("internal_error") }
    }

    func removeWebHost(_ host: String) async {
        guard let client else { return }
        do { _ = try await Task.detached { try client.removeWebHost(host) }.value; await loadWeb() } catch { webMessage = (error as? AtlasError)?.message }
    }

    /// Reads one page on an allowed site. The page is shown as untrusted text; it cannot add a site, change a setting or start anything.
    func readWebPage(_ address: String) async {
        guard let client else { return }
        webMessage = nil
        webPage = nil
        let url = address.trimmingCharacters(in: .whitespacesAndNewlines)
        do { webPage = WebOutcome.page(try await Task.detached { try client.readWebPage(url) }.value) } catch AtlasError.core(let code) { webMessage = WebOutcome.message(forCoreCode: code) } catch { webMessage = Catalogue.shared.error("internal_error") }
    }

    func loadConnections() async {
        guard let client else { return }
        do {
            connections = ConnectionsOutcome.from(try await Task.detached { try client.connectors() }.value)
            connectionsServed = true
        } catch AtlasError.core(let code) where code == "not_found" {
            connectionsServed = false
            connections = .idle
        } catch { connections = .failed((error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")) }
    }

    /// Connect, check or disconnect one integration. The token goes only to the Core, which keeps it in the Keychain; it is never shown again.
    func connect(_ id: String, draft: ConnectDraft) async -> Bool {
        guard let client, draft.problem() == nil else { return false }
        connectionMessage = nil
        let fields = draft.fields
        do {
            let answer = try await Task.detached { try client.connect(connector: id, address: fields["address"] ?? "", token: fields["token"] ?? "") }.value
            await loadConnections()
            guard let view = ConnectionsOutcome.view(from: answer), view.isConnected else {
                connectionMessage = ConnectionsOutcome.problem(answer["problem"] as? String)
                return false
            }
            if case .needsAttention(let why) = view.state { connectionMessage = why }
            return true
        } catch { connectionMessage = (error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error"); return false }
    }

    func checkConnection(_ id: String) async {
        guard let client else { return }
        connectionMessage = nil
        do { _ = try await Task.detached { try client.check(connector: id) }.value; await loadConnections() } catch { connectionMessage = (error as? AtlasError)?.message }
    }

    func disconnect(_ id: String) async {
        guard let client else { return }
        connectionMessage = nil
        do { _ = try await Task.detached { try client.disconnect(connector: id) }.value; await loadConnections() } catch { connectionMessage = (error as? AtlasError)?.message }
    }

    /// Dictation into the composer. The session owns the state and reports each change, which is published here so the button and the message follow along.
    func toggleVoice() {
        voice.onChange = { [weak self] state in self?.voiceState = state }
        voice.toggle()
    }

    /// The highlights are an ordinary question the Core started: wait for it like any answer and show it with its checks and citations. If the model is not available, say so.
    func loadHighlights(_ taskID: String) async {
        guard let client else { return }
        highlights = nil
        highlightsNote = "Writing your summary."
        do {
            while true {
                let state = try await Task.detached { try client.state(taskID) }.value
                let phase = TaskPhase.from(coreState: state)
                if phase.isTerminal || phase == .unknown { break }
                try await Task.sleep(nanoseconds: 500_000_000)
            }
            highlights = AnswerView(try await Task.detached { try client.answer(taskID) }.value)
            highlightsNote = nil
        } catch { highlightsNote = (error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error") }
    }

    /// Reads an answer aloud with the Mac's own voice; pressing again stops it.
    func readAloud(_ answer: AnswerView) {
        aloud.onChange = { [weak self] state in self?.reading = state == .speaking }
        aloud.toggle(AloudText.from(answer))
    }

    func runReview() async {
        guard let client else { return }
        review = .loading
        do {
            review = ReviewOutcome.from(try await Task.detached { try client.review() }.value)
        } catch AtlasError.core(let code) where code == "not_found" { review = .unavailable(.notAvailableYet)
        } catch { review = .failed((error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")) }
    }

    func loadUpdates() async {
        guard let client else { return }
        do {
            updates = UpdateOutcome.status(try await Task.detached { try client.updateStatus() }.value)
        } catch AtlasError.core(let code) where code == "not_found" {
            updates = .idle  // the Core does not manage its own install: the section stays hidden
        } catch { updates = .failed((error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")) }
    }

    func installUpdate(from folder: String) async {
        guard let client else { return }
        updateMessage = nil
        do {
            let response = try await Task.detached { try client.installUpdate(folder: folder) }.value
            updateMessage = UpdateOutcome.result(response).message
            await loadUpdates()
        } catch { updateMessage = (error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error") }
    }

    func rollBackUpdate() async {
        guard let client else { return }
        updateMessage = nil
        do {
            let response = try await Task.detached { try client.rollbackUpdate() }.value
            updateMessage = UpdateOutcome.result(response).message
            await loadUpdates()
        } catch { updateMessage = (error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error") }
    }

    /// Sources the owner could still turn on, from what the Core offers; each is a deliberate step and nothing is preselected.
    func enable(sourceType: String) async {
        guard let client else { return }
        failure = nil
        do { _ = try await Task.detached { try client.enable([sourceType]) }.value } catch { failure = (error as? AtlasError)?.message; return }
        await refreshConsent()
        await loadSettings()
        if sourceType == "finance" { await loadFinance() }
        if sourceType == "health" { await loadHealth() }
    }

    // MARK: own records

    func loadRecords(_ domain: OwnDomain) async {
        guard let client else { return }
        ownRecords[domain] = .loading
        let name = domain.rawValue
        do {
            let response = try await Task.detached { try client.records(name) }.value
            editsAvailable = true
            ownRecords[domain] = RecordsOutcome.from(response)
        } catch AtlasError.core(let code) where code == "not_found" {
            editsAvailable = false
            ownRecords[domain] = .unavailable(.notAvailableYet)
        } catch { ownRecords[domain] = .failed((error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error")) }
    }

    /// Does this Core serve the owner's own records at all? Decides whether the Calendar, Contacts and Notes areas are listed.
    func probeOwnRecords() async {
        guard let client else { return }
        editsAvailable = (try? await Task.detached { try client.records("notes") }.value) != nil
    }

    func add(_ draft: RecordDraft) async -> Bool {
        guard let client, let payload = draft.createPayload(id: RecordIdentity.make(domain: draft.domain), now: Date()) else { return false }
        let action = draft.domain.createAction
        do {
            let outcome = try await Task.detached { try client.act(action, payload: payload) }.value
            guard (outcome["status"] as? String) == "done" else { failure = "Atlas could not add that."; return false }
            undoActionID = outcome["action_id"] as? String
            undoLabel = "Added “\(draft.title)”."
            undoFailure = nil
            await loadRecords(draft.domain)
            await loadAttention()
            return true
        } catch { failure = (error as? AtlasError)?.message; return false }
    }

    func archive(_ record: OwnRecord, in domain: OwnDomain) async {
        guard let client else { return }
        let action = domain.archiveAction, payload: [String: Any] = ["id": record.id, "expected_version": record.version]
        do {
            let outcome = try await Task.detached { try client.act(action, payload: payload) }.value
            guard (outcome["status"] as? String) == "done" else { failure = "Atlas could not remove that."; return }
            undoActionID = outcome["action_id"] as? String
            undoLabel = "Removed “\(record.title)”."
            undoFailure = nil
            await loadRecords(domain)
            await loadAttention()
        } catch { failure = (error as? AtlasError)?.message }
    }

    func undoLast(domain: OwnDomain) async {
        guard let client, let id = undoActionID else { return }
        do {
            let outcome = try await Task.detached { try client.undo(actionID: id) }.value
            guard UndoConfirmation.isConfirmed(outcome) else {
                undoFailure = "Atlas could not confirm the undo. The original change may still be in place."
                return
            }
            undoActionID = nil
            undoLabel = nil
            undoFailure = nil
            await loadRecords(domain)
            await loadAttention()
        } catch {
            undoFailure = "Atlas could not confirm the undo. The original change may still be in place."
        }
    }

    func dismissUndo() { undoLabel = nil; undoActionID = nil; undoFailure = nil }

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
        submissionCancellation.begin()
        defer { submissionCancellation.end(); busy = false; gate.end() }
        do {
            let id = try await Task.detached { try client.ask(question: text, scope: sources) }.value
            let cancelImmediately = submissionCancellation.bind(id)
            turns[index].taskID = id
            question = ""
            if cancelImmediately {
                do { _ = try await Task.detached { try client.cancel(id) }.value }
                catch { failure = "Atlas could not stop this task yet." }
            }
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
        guard let client, busy else { return }
        guard let id = submissionCancellation.request() else { return }
        do { _ = try await Task.detached { try client.cancel(id) }.value }
        catch { failure = "Atlas could not stop this task yet." }
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
            let enabled = Set(grants.compactMap { $0["source_type"] as? String })
            offeredSources = (state["sources"] as? [[String: Any]] ?? []).compactMap { $0["source_type"] as? String }.filter { !enabled.contains($0) }
            let status = try await Task.detached { try client.indexStatus() }.value
            research = (try await Task.detached { try client.mode() }.value) == "research"
            indexLine = "Indexed \(status["indexed"] as? Int ?? 0) of \(status["total"] as? Int ?? 0), \(status["state"] as? String ?? "")."
            await loadDevices()
            await loadAttention()
            await probeOwnRecords()
            await loadFinance()
            await loadHealth()
            await loadConnections()
            await loadWeb()
            await loadUpdates()
        } catch { failure = (error as? AtlasError)?.message }
    }

    /// What needs the owner's attention, from the Core (computed by code from the owner's own records). If the Core has none or cannot say, the group stays hidden.
    func loadAttention() async {
        guard let client else { return }
        let raw = (try? await Task.detached { try client.attention() }.value) ?? []
        attention = raw.compactMap { ActivityItem.fromAttention($0, now: Date()) }
        await deliverNotifications()
    }

    /// Opt-in: the owner turns it on in Settings, and macOS asks once. Off by default; nothing is preselected.
    func setNotifications(_ on: Bool) async {
        if on {
            let granted = (try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert])) ?? false
            notificationsOn = granted
            if !granted { failure = "Notifications are off in macOS. You can allow them in System Settings." }
        } else { notificationsOn = false }
        UserDefaults.standard.set(notificationsOn, forKey: Self.notifyKey)
        await deliverNotifications()
    }

    /// Content-free notifications for items that need attention, once each.
    private func deliverNotifications() async {
        let plans = NotificationPlanner.plans(for: attention, alreadyNotified: notified, enabled: notificationsOn)
        for plan in plans {
            notified.insert(plan.id)
            let content = UNMutableNotificationContent()
            content.title = plan.title
            content.body = plan.body
            try? await UNUserNotificationCenter.current().add(UNNotificationRequest(identifier: plan.id, content: content, trigger: nil))
        }
    }

    /// Opens a pairing offer on the Core and builds the invite a phone reads. The address is where the owner's phone reaches this Mac (a private network name or a relay they run); it is remembered for next time.
    func showPairingInvite(address: String) async {
        guard let client else { return }
        UserDefaults.standard.set(address, forKey: "atlas.phoneAddress")
        pairingMessage = nil
        do {
            let offer = try await Task.detached { try client.openPairingOffer() }.value
            guard let invite = PairingInvite.make(offer: offer, address: address) else {
                pairingInvite = nil
                pairingMessage = "Enter the address your phone will use to reach this Mac. It starts with https, or http for your own home network."
                return
            }
            pairingInvite = invite.text
            pairingMessage = "The code works once and for five minutes."
        } catch { pairingMessage = (error as? AtlasError)?.message ?? Catalogue.shared.error("internal_error") }
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
