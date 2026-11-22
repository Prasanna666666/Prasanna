import AtlasKit
import CryptoKit
import Security
import SwiftUI

@main
struct AtlasApp: App {
    @StateObject private var model = ConversationModel()
    var body: some Scene {
        WindowGroup("Atlas") {
            if model.needsGetStarted { GetStartedView(model: model) } else { ConversationView(model: model) }
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
    private let socket = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Atlas/run/core.sock").path

    init() {
        client = (try? KeyStore.identity()).map { CoreClient(socketPath: socket, signer: $0.signer, clientID: $0.id) }
        Task { await refreshConsent() }
    }

    func refreshConsent() async {
        guard let client else { return }
        do {
            let state = try await Task.detached { try client.consent() }.value
            needsGetStarted = !((state["grants"] as? [[String: Any]]) ?? []).contains { ($0["revoked"] as? Bool) == false }
        } catch AtlasError.core(let code) where code == "unauthenticated" {
            // First run: the Core does not know this client yet. Enrol it as the owner client (accepted once, over the owner-only socket), then ask again.
            do { try await Task.detached { try client.enrolSelf() }.value; await refreshConsent() } catch { failure = (error as? AtlasError)?.message }
        } catch { failure = (error as? AtlasError)?.message }
    }

    func enable(_ sources: [String]) async {
        guard let client else { return }
        do { _ = try await Task.detached { try client.enable(sources) }.value; needsGetStarted = false } catch { failure = (error as? AtlasError)?.message }
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
    @State private var documents = true, mail = true
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Welcome to Atlas").font(.largeTitle)
            Text("Atlas answers from your own documents and mail, on this Mac. Nothing leaves your computer. Choose what Atlas may read. You can change this at any time.")
            Toggle("My documents", isOn: $documents)
            Toggle("My mail (message text only; attachments are not read)", isOn: $mail)
            if let failure = model.failure { Text(failure).foregroundStyle(.red) }
            Button("Continue") { Task { await model.enable((documents ? ["documents"] : []) + (mail ? ["mail"] : [])) } }
                .buttonStyle(.borderedProminent).disabled(!documents && !mail)
        }.padding(32).frame(minWidth: 520)
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
