import AtlasKit
import SwiftUI
import VisionKit

struct PhoneRoot: View {
    @ObservedObject var model: PhoneModel

    var body: some View {
        if model.isPaired {
            TabView {
                AskView(model: model).tabItem { Label("Ask", systemImage: "bubble.left.and.text.bubble.right") }
                AreasView(model: model).tabItem { Label("Areas", systemImage: "square.grid.2x2") }
                PhoneSettingsView(model: model).tabItem { Label("Settings", systemImage: "gearshape") }
            }
        } else {
            PairView(model: model)
        }
    }
}

struct LinkBanner: View {
    @ObservedObject var model: PhoneModel

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if model.link == .offline { Label("Your Mac cannot be reached. What you see may be old.", systemImage: "wifi.slash") }
            if model.pending > 0 { Label("\(model.pending) \(model.pending == 1 ? "change" : "changes") waiting to be sent.", systemImage: "clock") }
            if let text = model.message { Text(text).font(.footnote).foregroundStyle(.secondary) }
        }
        .font(.footnote)
    }
}

struct PairView: View {
    @ObservedObject var model: PhoneModel
    @State private var invite = ""
    @State private var scanning = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Pair with your Mac") {
                    Text("On your Mac, open Atlas, go to Settings and choose Pair a phone. Then scan the code, or paste the text it shows.")
                        .font(.callout)
                    TextField("Pairing code", text: $invite, axis: .vertical).textInputAutocapitalization(.never).autocorrectionDisabled()
                    if DataScannerViewController.isSupported && DataScannerViewController.isAvailable { Button("Scan the code") { scanning = true } }
                    Button("Pair") { Task { await model.pair(inviteText: invite, label: "My phone") } }.disabled(invite.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                if let text = model.message { Section { Text(text).foregroundStyle(.secondary) } }
            }
            .navigationTitle("Atlas")
            .sheet(isPresented: $scanning) { CodeScanner { text in invite = text; scanning = false } }
        }
    }
}

struct CodeScanner: UIViewControllerRepresentable {
    let found: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(found: found) }

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let scanner = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])], qualityLevel: .balanced, isHighlightingEnabled: true)
        scanner.delegate = context.coordinator
        try? scanner.startScanning()
        return scanner
    }

    func updateUIViewController(_ controller: DataScannerViewController, context: Context) {}

    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let found: (String) -> Void
        init(found: @escaping (String) -> Void) { self.found = found }
        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            for item in addedItems { if case .barcode(let code) = item, let text = code.payloadStringValue { found(text); return } }
        }
    }
}

struct AskView: View {
    @ObservedObject var model: PhoneModel
    @State private var question = ""

    var body: some View {
        NavigationStack {
            VStack(spacing: 12) {
                LinkBanner(model: model).frame(maxWidth: .infinity, alignment: .leading)
                List(model.turns) { turn in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(turn.question).font(.headline)
                        if turn.running { ProgressView() }
                        if let failure = turn.failure { Text(failure).foregroundStyle(.red) }
                        if let answer = turn.answer {
                            Text(answer.text)
                            if !answer.trust.isEmpty { Text(answer.trust).font(.footnote).foregroundStyle(.secondary) }
                            ForEach(answer.citations, id: \.id) { citation in Text(citation.label).font(.footnote).foregroundStyle(.secondary) }
                        }
                    }
                }
                HStack {
                    TextField("Ask Atlas", text: $question, axis: .vertical).textFieldStyle(.roundedBorder)
                    Button("Send") { let q = question; question = ""; Task { await model.ask(q, scope: ["documents", "mail"]) } }.disabled(question.trimmingCharacters(in: .whitespaces).isEmpty || model.busy)
                }
            }
            .padding()
            .navigationTitle("Ask")
        }
    }
}

struct AreasView: View {
    @ObservedObject var model: PhoneModel

    var body: some View {
        NavigationStack {
            List {
                Section { LinkBanner(model: model) }
                ForEach(OwnDomain.allCases, id: \.self) { domain in
                    NavigationLink(domain.title) { AreaView(model: model, domain: domain) }
                }
            }
            .navigationTitle("Areas")
        }
    }
}

struct AreaView: View {
    @ObservedObject var model: PhoneModel
    let domain: OwnDomain
    @State private var adding = false

    var body: some View {
        List {
            Section { LinkBanner(model: model) }
            switch model.readings[domain]?.state ?? .idle {
            case .loaded(let rows), .partial(let rows, _):
                ForEach(rows) { row in
                    VStack(alignment: .leading) {
                        Text(row.title).font(.headline)
                        let detail = row.detail(for: domain)
                        if !detail.isEmpty { Text(detail).font(.footnote).foregroundStyle(.secondary) }
                    }
                    .swipeActions { Button("Archive", role: .destructive) { Task { await model.archive(row, in: domain) } } }
                }
            case .empty: Text(domain.emptyText).foregroundStyle(.secondary)
            case .loading, .idle: ProgressView()
            case .unavailable(let reason): Text(reason.message).foregroundStyle(.secondary)
            case .denied(let text), .failed(let text): Text(text).foregroundStyle(.secondary)
            }
        }
        .navigationTitle(domain.title)
        .toolbar { Button("Add") { adding = true } }
        .sheet(isPresented: $adding) { AddView(model: model, domain: domain) { adding = false } }
        .task { await model.load(domain) }
        .refreshable { await model.load(domain) }
    }
}

struct AddView: View {
    @ObservedObject var model: PhoneModel
    let domain: OwnDomain
    let close: () -> Void
    @State private var draft: RecordDraft
    @State private var starts = Date()

    init(model: PhoneModel, domain: OwnDomain, close: @escaping () -> Void) {
        self.model = model; self.domain = domain; self.close = close
        _draft = State(initialValue: RecordDraft(domain: domain))
    }

    var body: some View {
        var current = draft
        let _ = { if domain.hasDates { current.starts = starts } }()
        NavigationStack {
            Form {
                TextField(domain == .contacts ? "Name" : "Title", text: $draft.title)
                switch domain {
                case .notes: TextField("Note", text: $draft.text, axis: .vertical)
                case .calendar, .travel: DatePicker("Starts", selection: $starts)
                case .contacts:
                    TextField("Phone (optional)", text: $draft.phone)
                    TextField("Email (optional)", text: $draft.email)
                }
                if let problem = current.problem() { Text(problem).font(.footnote).foregroundStyle(.secondary) }
            }
            .navigationTitle("Add to \(domain.title)")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel", action: close) }
                ToolbarItem(placement: .confirmationAction) { Button("Add") { let d = current; Task { await model.add(d); close() } }.disabled(current.problem() != nil) }
            }
        }
    }
}

struct PhoneSettingsView: View {
    @ObservedObject var model: PhoneModel
    @State private var confirming = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Connection") {
                    Text(model.link == .online ? "Connected to your Mac." : "Your Mac cannot be reached right now.")
                    if model.pending > 0 { Button("Send \(model.pending) waiting \(model.pending == 1 ? "change" : "changes") now") { Task { await model.sync() } } }
                    if let text = model.message { Text(text).font(.footnote).foregroundStyle(.secondary) }
                }
                Section {
                    Button("Unpair this phone", role: .destructive) { confirming = true }
                    Text("This erases the pairing, anything saved offline and every change still waiting on this phone. Your Mac is not changed.").font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Settings")
            .confirmationDialog("Unpair this phone?", isPresented: $confirming) { Button("Unpair", role: .destructive) { model.unpair() } }
        }
    }
}
