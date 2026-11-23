import AtlasKit
import Foundation

/// What the screens show. Every network call runs off the main thread; the engine decides what each answer means.
@MainActor
final class PhoneModel: ObservableObject {
    struct Turn: Identifiable { let id = UUID(); let question: String; var answer: AnswerView?; var failure: String?; var running = true }

    private let engine: PhoneEngine
    @Published var link: PhoneEngine.Link
    @Published var pending = 0
    @Published var message: String?
    @Published var readings: [OwnDomain: PhoneEngine.Reading] = [:]
    @Published var turns: [Turn] = []
    @Published var busy = false

    init() {
        engine = PhoneEngine(vault: KeychainVault(), queueStore: FileBlob(name: "queue"), cacheFor: { FileBlob(name: "cache-" + $0.rawValue) }, transportFor: { RemoteHTTP(address: $0) })
        link = engine.link
        pending = engine.pendingChanges
    }

    var isPaired: Bool { link != .notPaired && link != .revoked }

    private func refreshState() { link = engine.link; pending = engine.pendingChanges }

    func pair(inviteText: String, label: String) async {
        message = nil
        let engine = self.engine
        let outcome = await Task.detached { engine.pair(inviteText: inviteText, label: label) }.value
        if case .failed(let text) = outcome { message = text }
        refreshState()
    }

    func unpair() { engine.unpair(); readings = [:]; turns = []; refreshState() }

    func load(_ domain: OwnDomain) async {
        let engine = self.engine
        readings[domain] = await Task.detached { engine.records(domain) }.value
        refreshState()
        if link == .revoked { message = SyncOutcome.revoked.message }
    }

    func add(_ draft: RecordDraft) async {
        let engine = self.engine
        let outcome = await Task.detached { engine.add(draft) }.value
        message = outcome.message
        refreshState()
        await load(draft.domain)
    }

    func archive(_ record: OwnRecord, in domain: OwnDomain) async {
        let engine = self.engine
        let outcome = await Task.detached { engine.archive(record, in: domain) }.value
        message = outcome.message
        refreshState()
        await load(domain)
    }

    func sync() async {
        let engine = self.engine
        message = await Task.detached { engine.sync() }.value.message
        refreshState()
    }

    /// Ask the Mac a question. The Mac's model, sources and rules answer; with no connection the phone says so.
    func ask(_ question: String, scope: [String]) async {
        let text = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !busy else { return }
        busy = true
        turns.append(Turn(question: text))
        let index = turns.count - 1
        defer { busy = false }
        let engine = self.engine
        let started = await Task.detached { engine.ask(text, scope: scope) }.value
        refreshState()
        guard case .success(let id) = started, let client = engine.taskClient() else {
            turns[index].failure = SyncOutcome.offline.message.replacingOccurrences(of: "Your changes are saved and will be sent when it can.", with: "Questions need your Mac.")
            turns[index].running = false
            return
        }
        do {
            while true {
                let state = try await Task.detached { try client.state(id) }.value
                let phase = TaskPhase.from(coreState: state)
                if phase.isTerminal || phase == .unknown { break }
                try await Task.sleep(nanoseconds: 400_000_000)
            }
            turns[index].answer = AnswerView(try await Task.detached { try client.answer(id) }.value)
        } catch { turns[index].failure = (error as? AtlasError)?.message ?? "Atlas could not finish that." }
        turns[index].running = false
    }
}
