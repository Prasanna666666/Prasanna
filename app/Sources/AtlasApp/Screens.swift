import AppKit
import AtlasKit
import CoreImage.CIFilterBuiltins
import SwiftUI

// MARK: Home

struct HomeView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        let attention = ActivityFeed.needingAttention(model.activity + model.attention)
        let recent = ActivityFeed.recentTasks(model.activity)
        let updates = ActivityFeed.merged(model.activity).filter { $0.kind == .update || $0.kind == .action }.prefix(5)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.xl) {
                PageHeader(title: Greeting.text(hour: Calendar.current.component(.hour, from: Date())), subtitle: model.scopeLine)
                Button { model.select(.ask) } label: { Label("Ask Atlas", systemImage: "bubble.left.and.text.bubble.right").frame(maxWidth: .infinity, minHeight: Metrics.minimumHit) }
                    .buttonStyle(.borderedProminent).tint(theme.accent).controlSize(.large)
                reviewCard(theme)
                if attention.isEmpty && recent.isEmpty && updates.isEmpty {
                    StateNotice(text: model.scope.isEmpty
                        ? "Atlas reads nothing until you choose it. Turn on a source in Settings, then ask a question to begin."
                        : "Nothing needs your attention. Ask Atlas a question to get started.")
                }
                if !attention.isEmpty {
                    group("Needs your attention") { ForEach(attention) { ActivityRow(item: $0) } }
                }
                if !updates.isEmpty {
                    group("Recent updates") { ForEach(Array(updates)) { ActivityRow(item: $0) } }
                }
                if !recent.isEmpty {
                    group("Continue where you left off") { ForEach(recent) { ActivityRow(item: $0) } }
                }
            }
            .padding(Space.xl).readingColumn()
        }
        .task { await model.loadAttention() }
    }

    @ViewBuilder private func reviewCard(_ theme: Theme) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            HStack {
                Text("Your review").font(TextStyle.headline).accessibilityAddTraits(.isHeader)
                Spacer()
                Button(model.review.isIdle ? "Run review" : "Run again") { Task { await model.runReview() } }
            }
            switch model.review {
            case .idle: Text("A quick look at your calendar, finance and health, worked out on this Mac.").font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
            case .loading: StateNotice(text: "Reviewing.", style: .loading)
            case .loaded(let view), .partial(let view, _):
                ForEach(view.sections) { section in
                    VStack(alignment: .leading, spacing: Space.xs) {
                        Text(section.title).font(TextStyle.body).foregroundStyle(theme.textPrimary)
                        Text(section.summary).font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
                        if let id = section.taskID {
                            Button(model.highlights == nil ? "Show the summary" : "Refresh the summary") { Task { await model.loadHighlights(id) } }
                            if let note = model.highlightsNote { Text(note).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
                            if let answer = model.highlights {
                                Text(answer.text).font(TextStyle.body).foregroundStyle(theme.textPrimary)
                                if !answer.trust.isEmpty { Text(answer.trust).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
                                ForEach(answer.citations, id: \.id) { Text($0.label).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
                            }
                        }
                        if section.needsAction, section.id != "calendar" { Button("Turn on \(section.title)") { Task { await model.enable(sourceType: section.id); await model.runReview() } } }
                    }.accessibilityElement(children: .combine)
                }
                if let note = view.note { Text(note).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
            case .unavailable(let reason): StateNotice(text: reason.message, style: .warning)
            case .failed(let text): StateNotice(text: text, style: .problem)
            case .empty, .denied: EmptyView()
            }
        }
    }

    @ViewBuilder private func group<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text(title).font(TextStyle.headline).accessibilityAddTraits(.isHeader)
            content()
        }
    }
}

// MARK: Ask Atlas

struct AskView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: Space.xl) {
                        PageHeader(title: "Ask Atlas", subtitle: model.scopeLine)
                        if model.turns.isEmpty {
                            StateNotice(text: model.scope.isEmpty
                                ? "No sources are enabled, so Atlas has nothing to search. Turn on a source in Settings."
                                : "Ask about your own documents or mail. Atlas answers on this Mac and shows where each answer comes from.")
                        }
                        ForEach(model.turns) { turn in TurnView(model: model, turn: turn).id(turn.id) }
                    }
                    .padding(Space.xl).readingColumn()
                }
                .onChange(of: model.turns.count) { _, _ in if let last = model.turns.last { withAnimation { proxy.scrollTo(last.id, anchor: .bottom) } } }
            }
            Divider()
            Composer(model: model).padding(Space.lg).readingColumn().background(theme.background)
        }
    }
}

struct TurnView: View {
    @ObservedObject var model: AppModel
    let turn: Turn
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        VStack(alignment: .leading, spacing: Space.md) {
            Text(turn.question).font(TextStyle.body).foregroundStyle(theme.textPrimary)
                .padding(Space.md).background(theme.surface, in: RoundedRectangle(cornerRadius: Radius.medium)).accessibilityLabel("You asked: \(turn.question)")
            if let phase = turn.phase, turn.answer == nil || !phase.isTerminal { PhaseLabel(phase: phase) }
            if let message = turn.failure { StateNotice(text: message + " Your question is still in the box so you can try again.", style: .problem) }
            if let answer = turn.answer {
                Text(answer.text).font(TextStyle.body).textSelection(.enabled).foregroundStyle(theme.textPrimary).accessibilityLabel("Atlas answered: \(answer.text)")
                Text(answer.trust).font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
                Button { model.readAloud(answer) } label: { Label(model.reading ? "Stop reading" : "Read aloud", systemImage: model.reading ? "speaker.slash" : "speaker.wave.2") }
                    .buttonStyle(.borderless).accessibilityHint("Reads the answer with your Mac's voice. Nothing is sent anywhere.")
                ForEach(answer.notices, id: \.self) { StateNotice(text: $0, style: .warning) }
                ForEach(answer.notSearched, id: \.self) { StateNotice(text: $0, style: .info) }
                if answer.citations.isEmpty { Text(Catalogue.shared.noCitations).font(TextStyle.secondary).foregroundStyle(theme.textMuted) }
                if !answer.citations.isEmpty {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: Space.sm, alignment: .leading)], alignment: .leading, spacing: Space.sm) {
                        ForEach(answer.citations) { citation in CitationChip(label: citation.label) { Task { await model.showEvidence(turn: turn, citation: citation) } } }
                    }
                }
                Group {
                    if let coverage = answer.coverageLine { Text(coverage) }
                    Text(answer.modelLine)
                }.font(TextStyle.caption).foregroundStyle(theme.textMuted)
            }
        }
    }
}

struct Composer: View {
    @ObservedObject var model: AppModel
    @FocusState private var focused: Bool
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        VStack(alignment: .leading, spacing: Space.sm) {
            if let notice = model.failure, model.turns.last?.failure != nil { Text(notice).font(TextStyle.caption).foregroundStyle(theme.destructive) }
            HStack(alignment: .bottom, spacing: Space.md) {
                TextEditor(text: $model.question)
                    .font(TextStyle.body)
                    .focused($focused)
                    .frame(minHeight: 44, maxHeight: 140)
                    .scrollContentBackground(.hidden)
                    .padding(Space.sm)
                    .background(theme.surface, in: RoundedRectangle(cornerRadius: Radius.medium))
                    .accessibilityLabel("Your question")
                    .accessibilityHint("Press Return to send, or Shift and Return for a new line")
                    .onKeyPress(.return, phases: .down) { press in
                        if press.modifiers.contains(.shift) { return .ignored }
                        Task { await model.ask() }
                        return .handled
                    }
                if model.voice.availability.isAvailable {
                    Button { model.toggleVoice() } label: { Image(systemName: model.voiceState.isListening ? "mic.fill" : "mic") }
                        .accessibilityLabel(model.voiceState.isListening ? "Stop dictating" : "Dictate your question")
                        .keyboardShortcut("d", modifiers: [.command, .shift])
                }
                if model.busy {
                    Button("Stop") { Task { await model.cancel() } }.keyboardShortcut(".", modifiers: .command)
                } else {
                    Button("Send") { Task { await model.ask() } }
                        .buttonStyle(.borderedProminent).tint(theme.accent)
                        .disabled(model.question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.scope.isEmpty)
                }
            }
            if case .failed(let why) = model.voiceState { Text(why).font(TextStyle.caption).foregroundStyle(theme.destructive) }
            Text(model.scopeLine).font(TextStyle.caption).foregroundStyle(theme.textMuted)
        }
        .onAppear { focused = true }
    }
}

// MARK: Library

struct LibraryView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                PageHeader(title: "Library", subtitle: model.scopeLine)
                HStack {
                    TextField("Search your sources", text: $model.libraryQuery)
                        .textFieldStyle(.roundedBorder)
                        .accessibilityLabel("Search your sources")
                        .onSubmit { Task { await model.searchLibrary() } }
                    Button("Search") { Task { await model.searchLibrary() } }.disabled(model.libraryQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
                content(theme)
            }
            .padding(Space.xl).readingColumn()
        }
    }

    @ViewBuilder private func content(_ theme: Theme) -> some View {
        switch model.library {
        case .idle:
            StateNotice(text: "Search the documents and mail you enabled. Results show where each match comes from and how much of each source Atlas has read.")
        case .loading:
            StateNotice(text: "Searching.", style: .loading)
        case .empty:
            StateNotice(text: "No matches. Atlas searched everything it has read in the sources you enabled.")
        case .unavailable(let reason):
            StateNotice(text: reason.message, style: .warning)
        case .denied(let text):
            StateNotice(text: text, style: .warning)
        case .failed(let text):
            StateNotice(text: text, style: .problem)
        case .loaded(let page):
            results(page, note: nil, theme)
        case .partial(let page, let note):
            results(page, note: note, theme)
        }
    }

    @ViewBuilder private func results(_ page: LibraryPage, note: String?, _ theme: Theme) -> some View {
        if let note { StateNotice(text: note, style: .warning) }
        HStack {
            Picker("Show", selection: $model.libraryFilter) {
                Text("All sources").tag(String?.none)
                ForEach(page.types, id: \.self) { type in Text(Catalogue.shared.sourceKinds[type] ?? type).tag(Optional(type)) }
            }.fixedSize()
            Picker("Sort by", selection: $model.librarySort) { ForEach(LibrarySort.allCases, id: \.self) { Text($0.rawValue).tag($0) } }.fixedSize()
        }
        ForEach(model.librarySort.apply(page.results).filter { model.libraryFilter == nil || $0.sourceType == model.libraryFilter }) { row in
            VStack(alignment: .leading, spacing: Space.xs) {
                Text(row.title).font(TextStyle.headline).foregroundStyle(theme.textPrimary)
                Text("\(row.kind), \(row.place)").font(TextStyle.caption).foregroundStyle(theme.textMuted)
                Text(row.excerpt).font(TextStyle.body).foregroundStyle(theme.textSecondary)
            }
            .padding(.vertical, Space.sm)
            .accessibilityElement(children: .combine)
            Divider()
        }
    }
}

// MARK: Calendar, Contacts and Notes

struct RecordsView: View {
    @ObservedObject var model: AppModel
    let domain: OwnDomain
    @State private var adding = false
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        let state = model.ownRecords[domain] ?? .idle
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                HStack {
                    PageHeader(title: domain.title, subtitle: "Your own \(domain.title.lowercased()). Atlas can use these to answer and to point things out.")
                    Button { adding = true } label: { Label("Add", systemImage: "plus") }.keyboardShortcut("n", modifiers: .command)
                }
                if let label = model.undoLabel {
                    VStack(alignment: .leading, spacing: Space.xs) {
                        HStack {
                            Label(label, systemImage: "checkmark.circle").foregroundStyle(theme.textSecondary)
                            Spacer()
                            Button("Undo") { Task { await model.undoLast(domain: domain) } }
                            Button("Dismiss") { model.dismissUndo() }
                        }
                        if let message = model.undoFailure {
                            Text(message).font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
                        }
                    }.padding(Space.md).background(theme.surface, in: RoundedRectangle(cornerRadius: Radius.medium))
                }
                switch state {
                case .loaded(let rows), .partial(let rows, _):
                    ForEach(rows) { row in
                        HStack(alignment: .top) {
                            VStack(alignment: .leading, spacing: Space.xs) {
                                Text(row.title).font(TextStyle.headline).foregroundStyle(theme.textPrimary)
                                let detail = row.detail(for: domain)
                                if !detail.isEmpty { Text(detail).font(TextStyle.secondary).foregroundStyle(theme.textSecondary).lineLimit(3) }
                            }
                            Spacer()
                            Button("Remove", role: .destructive) { Task { await model.archive(row, in: domain) } }.help("Removes it. You can undo this right away.")
                        }
                        .padding(.vertical, Space.sm)
                        .accessibilityElement(children: .combine)
                        Divider()
                    }
                case .empty: StateNotice(text: domain.emptyText)
                case .loading, .idle: StateNotice(text: "Loading.", style: .loading)
                case .unavailable(let reason): StateNotice(text: reason.message, style: .warning)
                case .denied(let text): StateNotice(text: text, style: .warning)
                case .failed(let text): StateNotice(text: text, style: .problem)
                }
            }
            .padding(Space.xl).readingColumn()
        }
        .task(id: domain) { await model.loadRecords(domain) }
        .sheet(isPresented: $adding) { AddRecordSheet(model: model, domain: domain, close: { adding = false }) }
    }
}

struct AddRecordSheet: View {
    @ObservedObject var model: AppModel
    let domain: OwnDomain
    let close: () -> Void
    @State private var draft: RecordDraft
    @State private var startsOn = Date()
    @State private var hasEnd = false
    @State private var endsOn = Date().addingTimeInterval(3600)
    @Environment(\.colorScheme) private var scheme

    init(model: AppModel, domain: OwnDomain, close: @escaping () -> Void) {
        self.model = model; self.domain = domain; self.close = close
        _draft = State(initialValue: RecordDraft(domain: domain))
    }

    var body: some View {
        let theme = Theme(scheme)
        var current = draft
        let _ = { if domain.hasDates { current.starts = startsOn; current.ends = hasEnd ? endsOn : nil } }()
        VStack(alignment: .leading, spacing: Space.lg) {
            Text("Add to \(domain.title)").font(TextStyle.title).accessibilityAddTraits(.isHeader)
            TextField(domain == .contacts ? "Name" : (domain == .travel ? "Where to" : "Title"), text: $draft.title).textFieldStyle(.roundedBorder)
            switch domain {
            case .notes:
                TextEditor(text: $draft.text).frame(minHeight: 120).padding(Space.xs).background(theme.surface, in: RoundedRectangle(cornerRadius: Radius.small)).accessibilityLabel("Note")
            case .calendar, .travel:
                DatePicker("Starts", selection: $startsOn)
                Toggle("Has an end", isOn: $hasEnd)
                if hasEnd { DatePicker("Ends", selection: $endsOn) }
                if domain == .calendar { TextField("Where (optional)", text: $draft.location).textFieldStyle(.roundedBorder) }
                if domain == .travel { TextField("Booking reference (optional)", text: $draft.booking).textFieldStyle(.roundedBorder) }
            case .contacts:
                TextField("Phone (optional)", text: $draft.phone).textFieldStyle(.roundedBorder)
                TextField("Email (optional)", text: $draft.email).textFieldStyle(.roundedBorder)
            }
            if let problem = current.problem() { Text(problem).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
            HStack {
                Button("Cancel", action: close).keyboardShortcut(.cancelAction)
                Spacer()
                Button("Add") { Task { if await model.add(current) { close() } } }.disabled(current.problem() != nil).keyboardShortcut(.defaultAction)
            }
        }
        .padding(Space.xl).frame(minWidth: 420)
    }
}

// MARK: Finance

struct FinanceAreaView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                PageHeader(title: "Finance", subtitle: "Spending, added up on this Mac from your own transactions.")
                switch model.finance {
                case .loaded(let view), .partial(let view, _):
                    VStack(alignment: .leading, spacing: Space.xs) {
                        Text(view.monthTitle).font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
                        Text(view.total).font(.system(size: 34, weight: .semibold).monospacedDigit()).foregroundStyle(theme.textPrimary)
                            .accessibilityLabel("Spent in \(view.monthTitle): \(view.total)")
                        if let change = view.changeLine { Text(change).font(TextStyle.secondary).foregroundStyle(theme.textSecondary) }
                    }
                    if !view.categories.isEmpty { lines("By category", view.categories, theme) }
                    if view.months.count > 1 { lines("Month by month", view.months, theme) }
                    Text(view.basis).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                case .empty: StateNotice(text: "No transactions yet. Import your Finance data to see spending here.")
                case .denied(let text): StateNotice(text: text, style: .warning, actionTitle: "Turn on Finance") { Task { await model.enable(sourceType: "finance") } }
                case .loading, .idle: StateNotice(text: "Loading.", style: .loading)
                case .unavailable(let reason): StateNotice(text: reason.message, style: .warning)
                case .failed(let text): StateNotice(text: text, style: .problem)
                }
            }
            .padding(Space.xl).readingColumn()
        }
        .task { await model.loadFinance() }
    }

    @ViewBuilder private func lines(_ title: String, _ rows: [FinanceView.Line], _ theme: Theme) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text(title).font(TextStyle.headline).accessibilityAddTraits(.isHeader)
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack { Text(row.label); Spacer(); Text(row.amount).monospacedDigit() }
                    .font(TextStyle.body).foregroundStyle(theme.textPrimary).accessibilityElement(children: .combine)
                Divider()
            }
        }
    }
}

// MARK: Web

struct WebView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme
    @State private var newHost = ""
    @State private var address = ""

    private var hosts: [String] { if case .loaded(let list) = model.webHosts { return list } else { return [] } }

    var body: some View {
        let theme = Theme(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                PageHeader(title: "Web", subtitle: "Atlas opens only the sites you allow, in a separate browser, and shows what it finds as text. It never acts on what a page says.")
                if let message = model.webMessage { StateNotice(text: message, style: .warning) }
                Text("Allowed sites").font(TextStyle.headline).accessibilityAddTraits(.isHeader)
                if hosts.isEmpty { Text("No sites are allowed yet.").foregroundStyle(theme.textSecondary) }
                ForEach(hosts, id: \.self) { host in
                    HStack { Label(host, systemImage: "globe"); Spacer(); Button("Remove", role: .destructive) { Task { await model.removeWebHost(host) } } }
                }
                HStack {
                    TextField("Add a site, such as example.org", text: $newHost).textFieldStyle(.roundedBorder)
                    Button("Allow") { Task { await model.addWebHost(newHost); newHost = "" } }.disabled(WebOutcome.hostProblem(newHost) != nil)
                }
                if !newHost.isEmpty, let problem = WebOutcome.hostProblem(newHost) { Text(problem).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
                Divider()
                Text("Read a page").font(TextStyle.headline).accessibilityAddTraits(.isHeader)
                HStack {
                    TextField("Page address, starting with https", text: $address).textFieldStyle(.roundedBorder)
                    Button("Read") { Task { await model.readWebPage(address) } }.disabled(WebOutcome.problem(address: address, hosts: hosts) != nil)
                }
                if !address.isEmpty, let problem = WebOutcome.problem(address: address, hosts: hosts) { Text(problem).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
                if let page = model.webPage {
                    VStack(alignment: .leading, spacing: Space.sm) {
                        Text(page.note).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                        ForEach(page.warnings, id: \.self) { StateNotice(text: $0, style: .warning) }
                        Text(page.text).font(TextStyle.body).textSelection(.enabled).foregroundStyle(theme.textPrimary)
                    }
                }
            }
            .padding(Space.xl).readingColumn()
        }
        .task { await model.loadWeb() }
    }
}

// MARK: Connections

struct ConnectionsView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme
    @State private var connecting: ConnectorView?

    var body: some View {
        let theme = Theme(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                PageHeader(title: "Connections", subtitle: "Services you choose to connect. Atlas asks you first for anything that sends, spends or unlocks.")
                if let message = model.connectionMessage { StateNotice(text: message, style: .warning) }
                switch model.connections {
                case .loaded(let items), .partial(let items, _):
                    ForEach(items) { card($0, theme) }
                case .empty: StateNotice(text: "No services are available to connect yet.")
                case .loading, .idle: StateNotice(text: "Loading.", style: .loading)
                case .unavailable(let reason): StateNotice(text: reason.message, style: .warning)
                case .denied(let text), .failed(let text): StateNotice(text: text, style: .problem)
                }
            }
            .padding(Space.xl).readingColumn()
        }
        .task { await model.loadConnections() }
        .sheet(item: $connecting) { item in ConnectSheet(model: model, connector: item) { connecting = nil } }
    }

    @ViewBuilder private func card(_ item: ConnectorView, _ theme: Theme) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            HStack {
                Text(item.title).font(TextStyle.headline).accessibilityAddTraits(.isHeader)
                Spacer()
                Text(item.stateLine).font(TextStyle.caption).foregroundStyle(item.isConnected ? theme.textSecondary : theme.textMuted)
            }
            Text(item.summary).font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
            DisclosureGroup("What it can do") {
                VStack(alignment: .leading, spacing: Space.xs) {
                    Text("Atlas can read: \(item.reads).").font(TextStyle.secondary)
                    ForEach(item.changes, id: \.title) { change in Text("\(change.title). \(change.approvalNote)").font(TextStyle.secondary) }
                    Text(item.offline).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                    Text(item.retention).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                    Text(item.failure).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                }.padding(.top, Space.xs)
            }
            HStack {
                if item.isConnected {
                    Button("Check") { Task { await model.checkConnection(item.id) } }
                    Button("Disconnect", role: .destructive) { Task { await model.disconnect(item.id) } }
                } else {
                    Button("Connect…") { connecting = item }.buttonStyle(.borderedProminent).tint(theme.accent)
                }
            }
            Divider()
        }
        .accessibilityElement(children: .contain)
    }
}

struct ConnectSheet: View {
    @ObservedObject var model: AppModel
    let connector: ConnectorView
    let close: () -> Void
    @State private var draft = ConnectDraft()
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        VStack(alignment: .leading, spacing: Space.lg) {
            Text("Connect \(connector.title)").font(TextStyle.title).accessibilityAddTraits(.isHeader)
            TextField("Address of the service", text: $draft.address).textFieldStyle(.roundedBorder)
            SecureField("Access token", text: $draft.token).textFieldStyle(.roundedBorder)
            Text("The token is kept in your Mac's Keychain and is never shown again.").font(TextStyle.caption).foregroundStyle(theme.textMuted)
            if let problem = draft.problem() { Text(problem).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
            HStack {
                Button("Cancel", action: close).keyboardShortcut(.cancelAction)
                Spacer()
                Button("Connect") { Task { if await model.connect(connector.id, draft: draft) { close() } } }.disabled(draft.problem() != nil).keyboardShortcut(.defaultAction)
            }
        }
        .padding(Space.xl).frame(minWidth: 420)
    }
}

// MARK: Health

struct HealthAreaView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                PageHeader(title: "Health", subtitle: "Your readings, summarised on this Mac. Atlas does not give medical advice.")
                switch model.health {
                case .loaded(let view), .partial(let view, _):
                    ForEach(Array(view.measures.enumerated()), id: \.offset) { _, measure in
                        VStack(alignment: .leading, spacing: Space.xs) {
                            Text(measure.title).font(TextStyle.headline).accessibilityAddTraits(.isHeader)
                            Text(measure.latestLine).font(TextStyle.body).foregroundStyle(theme.textPrimary)
                            Text(measure.rangeLine).font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
                            Text(measure.averageLine).font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
                            Text(measure.basisLine).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                            Divider()
                        }
                        .accessibilityElement(children: .combine)
                    }
                    Text(view.basis).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                case .empty: StateNotice(text: "No readings yet. Import your Health data to see a summary here.")
                case .denied(let text): StateNotice(text: text, style: .warning, actionTitle: "Turn on Health") { Task { await model.enable(sourceType: "health") } }
                case .loading, .idle: StateNotice(text: "Loading.", style: .loading)
                case .unavailable(let reason): StateNotice(text: reason.message, style: .warning)
                case .failed(let text): StateNotice(text: text, style: .problem)
                }
            }
            .padding(Space.xl).readingColumn()
        }
        .task { await model.loadHealth() }
    }
}

// MARK: Activity

struct ActivityView: View {
    @ObservedObject var model: AppModel

    var body: some View {
        let items = ActivityFeed.merged(model.activity)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.lg) {
                PageHeader(title: "Activity", subtitle: "Questions you asked, and what needs your decision.")
                if items.isEmpty {
                    StateNotice(text: "Nothing has happened yet. When you ask Atlas a question, or something needs your decision, it appears here.")
                } else {
                    ForEach(items) { ActivityRow(item: $0); Divider() }
                }
            }
            .padding(Space.xl).readingColumn()
        }
    }
}

// MARK: Get Started

struct GetStartedView: View {
    @ObservedObject var model: AppModel
    @State private var choice = GetStartedChoice()  // everything off: only a deliberate choice creates a grant
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        VStack(alignment: .leading, spacing: Space.lg) {
            Text("Welcome to Atlas").font(.largeTitle).accessibilityAddTraits(.isHeader)
            // Two short paragraphs with the same words and order (was one long one): the hosted audit flagged the single paragraph while its
            // rendered pixels measured 14.94:1, so the layout is the variable under test (architect review 6094252873, option b).
            Text("Atlas answers from your own documents and mail, on this Mac. Nothing leaves your computer.")
                .foregroundStyle(.primary).fixedSize(horizontal: false, vertical: true)
            Text("Atlas reads nothing until you choose it here, and you can change this at any time in Settings.")
                .foregroundStyle(.primary).fixedSize(horizontal: false, vertical: true)
            Toggle("My documents", isOn: $choice.documents)
            Toggle("My mail (message text only; attachments are not read)", isOn: $choice.mail)
            if let failure = model.failure { StateNotice(text: failure, style: .problem) }
            Button(choice.sources.isEmpty ? "Continue without enabling anything" : "Continue") { Task { await model.complete(choice) } }
                .buttonStyle(.borderedProminent).tint(theme.accent).controlSize(.large)
        }
        .padding(Space.xxl)
        .frame(maxWidth: Metrics.readingWidth)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Welcome to Atlas. Choose what Atlas may read.")  // the audit found this container without a description
        .accessibilityIdentifier("get-started-\(scheme == .dark ? "dark" : "light")")  // the effective appearance, which the UI audit asserts
    }
}

// MARK: Settings

struct SettingsView: View {
    @ObservedObject var model: AppModel
    @State private var relayBind = UserDefaults.standard.string(forKey: "atlas.relayBind") ?? ""
    @State private var relayNote: String?
    @State private var phoneAddress = UserDefaults.standard.string(forKey: "atlas.phoneAddress") ?? ""
    @Environment(\.colorScheme) private var scheme

    /// Updates: shown only when the Core manages its own install. The owner chooses a folder that holds a signed release; the Core checks it, installs it beside the current version and keeps that version to go back to.
    @ViewBuilder private func updatesSection(_ theme: Theme) -> some View {
        if case .loaded(let view) = model.updates {
            VStack(alignment: .leading, spacing: Space.sm) {
                Text("Updates").font(TextStyle.headline).accessibilityAddTraits(.isHeader)
                Text(view.installedLine).font(TextStyle.secondary).foregroundStyle(theme.textSecondary)
                HStack {
                    Button("Install an update…") { chooseUpdateFolder() }
                    if view.canRollBack { Button("Go back to the previous version") { Task { await model.rollBackUpdate() } } }
                }
                if let message = model.updateMessage { Text(message).font(TextStyle.caption).foregroundStyle(theme.textSecondary) }
                Text("Updates are checked for a signature before anything is installed. Your data is never changed.").font(TextStyle.caption).foregroundStyle(theme.textMuted)
            }
        }
    }

    private func saveRelay() {
        if relayBind.trimmingCharacters(in: .whitespaces).isEmpty {
            UserDefaults.standard.removeObject(forKey: "atlas.relayBind")
            relayNote = "The phone channel is off. This takes effect the next time Atlas starts."
        } else if let bind = RelayBind.parse(relayBind) {
            UserDefaults.standard.set(bind, forKey: "atlas.relayBind")
            relayNote = "Saved. The phone channel starts the next time Atlas starts."
        } else { relayNote = RelayBind.explanation }
    }

    private func chooseUpdateFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Install"
        panel.message = "Choose the folder that holds the signed update."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        Task { await model.installUpdate(from: url.path) }
    }

    var body: some View {
        let theme = Theme(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.xl) {
                PageHeader(title: "Settings", subtitle: "What Atlas may read, and how it runs on this Mac.")
                section("Sources and access") {
                    if model.grants.isEmpty { Text("Nothing is enabled. Atlas reads nothing.").foregroundStyle(theme.textSecondary) }
                    ForEach(Array(model.grants.enumerated()), id: \.offset) { _, grant in
                        HStack {
                            Label(SourceNames.title(grant["source_type"] as? String ?? ""), systemImage: "checkmark.circle")
                            Spacer()
                            Button("Stop reading this", role: .destructive) { Task { await model.withdraw(grant["grant_id"] as? String ?? "") } }
                        }
                    }
                    ForEach(model.offeredSources, id: \.self) { type in
                        VStack(alignment: .leading, spacing: Space.xs) {
                            HStack {
                                Label(SourceNames.title(type), systemImage: "plus.circle")
                                Spacer()
                                Button("Turn on") { Task { await model.enable(sourceType: type) } }
                            }
                            Text(SourceNames.explanation(type)).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                        }
                    }
                    updatesSection(theme)
                    Text(model.indexLine).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                    Text("Stopping takes effect at once and removes what Atlas learned from that source.").font(TextStyle.caption).foregroundStyle(theme.textMuted)
                }
                section("Privacy") {
                    Text("Atlas works on this Mac. Your questions and your sources are never sent to a cloud service.").foregroundStyle(theme.textSecondary)
                }
                section("Local models and runtime") {
                    Toggle("Research mode (slower, for harder questions)", isOn: Binding(get: { model.research }, set: { value in Task { await model.setResearch(value) } }))
                    Text("Research mode switches off again when Atlas restarts.").font(TextStyle.caption).foregroundStyle(theme.textMuted)
                }
                section("Pair a phone") {
                    TextField("Address your phone will use", text: $phoneAddress).textFieldStyle(.roundedBorder)
                    Text("A private network name (for example from your VPN) or a relay you run. Atlas never opens a public port.").font(TextStyle.caption).foregroundStyle(theme.textMuted)
                    TextField("Let my phone connect on (private address and port)", text: $relayBind).textFieldStyle(.roundedBorder)
                    HStack {
                        Button("Save") { saveRelay() }
                        Text(relayNote ?? (RelayBind.parse(relayBind) == nil && !relayBind.isEmpty ? RelayBind.explanation : "Takes effect the next time Atlas starts. Leave it empty to keep the phone channel off.")).font(TextStyle.caption).foregroundStyle(theme.textMuted)
                    }
                    Button("Show pairing code") { Task { await model.showPairingInvite(address: phoneAddress) } }
                    if let invite = model.pairingInvite {
                        if let image = QRCode.image(for: invite) { Image(nsImage: image).interpolation(.none).resizable().frame(width: 180, height: 180).accessibilityLabel("Pairing code for your phone") }
                        Text(invite).font(.system(.caption, design: .monospaced)).textSelection(.enabled).foregroundStyle(theme.textSecondary)
                    }
                    if let note = model.pairingMessage { Text(note).font(TextStyle.caption).foregroundStyle(theme.textMuted) }
                }
                section("Connected devices and security") {
                    if model.devices.isEmpty { Text("No other devices are connected.").foregroundStyle(theme.textSecondary) }
                    ForEach(model.devices) { device in
                        HStack {
                            Label(device.label, systemImage: device.revoked ? "xmark.circle" : "iphone")
                            if device.revoked { Text("Removed").font(TextStyle.caption).foregroundStyle(theme.textMuted) }
                            Spacer()
                            if !device.revoked { Button("Remove this device", role: .destructive) { Task { await model.revoke(device: device) } } }
                        }
                    }
                }
                section("Notifications") {
                    Toggle("Tell me when something needs my attention", isOn: Binding(get: { model.notificationsOn }, set: { value in Task { await model.setNotifications(value) } }))
                    Text("Notifications never include your content: they only say that something needs you.").font(TextStyle.caption).foregroundStyle(theme.textMuted)
                }
                section("Appearance and accessibility") {
                    Text("Atlas follows your Mac's light or dark appearance, text size and Reduce Motion setting.").foregroundStyle(theme.textSecondary)
                }
                section("Diagnostics") {
                    Text(model.launch.message ?? "Atlas is running.").foregroundStyle(theme.textSecondary)
                    Text("Diagnostics never include your questions, documents or mail.").font(TextStyle.caption).foregroundStyle(theme.textMuted)
                }
                if let failure = model.failure { StateNotice(text: failure, style: .problem) }
            }
            .padding(Space.xl).readingColumn()
        }
        .task { await model.loadSettings() }
    }

    @ViewBuilder private func section<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: Space.sm) {
            Text(title).font(TextStyle.headline).accessibilityAddTraits(.isHeader)
            content()
            Divider()
        }
    }
}


/// A QR code of the pairing invite, drawn locally.
enum QRCode {
    static func image(for text: String) -> NSImage? {
        let filter = CIFilter.qrCodeGenerator()
        filter.message = Data(text.utf8)
        filter.correctionLevel = "M"
        guard let output = filter.outputImage?.transformed(by: CGAffineTransform(scaleX: 8, y: 8)) else { return nil }
        let rep = NSCIImageRep(ciImage: output)
        let image = NSImage(size: rep.size)
        image.addRepresentation(rep)
        return image
    }
}
