import AtlasKit
import SwiftUI

// MARK: Home

struct HomeView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        let attention = ActivityFeed.needingAttention(model.activity)
        let recent = ActivityFeed.recentTasks(model.activity)
        let updates = ActivityFeed.merged(model.activity).filter { $0.kind == .update || $0.kind == .action }.prefix(5)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.xl) {
                PageHeader(title: Greeting.text(hour: Calendar.current.component(.hour, from: Date())), subtitle: model.scopeLine)
                Button { model.select(.ask) } label: { Label("Ask Atlas", systemImage: "bubble.left.and.text.bubble.right").frame(maxWidth: .infinity, minHeight: Metrics.minimumHit) }
                    .buttonStyle(.borderedProminent).tint(theme.accent).controlSize(.large)
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
                if model.busy {
                    Button("Stop") { Task { await model.cancel() } }.keyboardShortcut(".", modifiers: .command)
                } else {
                    Button("Send") { Task { await model.ask() } }
                        .buttonStyle(.borderedProminent).tint(theme.accent)
                        .disabled(model.question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.scope.isEmpty)
                }
            }
            Text(model.scopeLine).font(TextStyle.caption).foregroundStyle(theme.textMuted)
        }
        .onAppear { focused = true }
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
            Text("Atlas answers from your own documents and mail, on this Mac. Nothing leaves your computer. Atlas reads nothing until you choose it here, and you can change this at any time in Settings.")
                .foregroundStyle(theme.textSecondary)
            Toggle("My documents", isOn: $choice.documents)
            Toggle("My mail (message text only; attachments are not read)", isOn: $choice.mail)
            if let failure = model.failure { StateNotice(text: failure, style: .problem) }
            Button(choice.sources.isEmpty ? "Continue without enabling anything" : "Continue") { Task { await model.complete(choice) } }
                .buttonStyle(.borderedProminent).tint(theme.accent).controlSize(.large)
        }
        .padding(Space.xxl)
        .frame(maxWidth: Metrics.readingWidth)
    }
}

// MARK: Settings

struct SettingsView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        ScrollView {
            VStack(alignment: .leading, spacing: Space.xl) {
                PageHeader(title: "Settings", subtitle: "What Atlas may read, and how it runs on this Mac.")
                section("Sources and access") {
                    if model.grants.isEmpty { Text("Nothing is enabled. Atlas reads nothing.").foregroundStyle(theme.textSecondary) }
                    ForEach(Array(model.grants.enumerated()), id: \.offset) { _, grant in
                        HStack {
                            Label(Catalogue.shared.sourceKinds[grant["source_type"] as? String ?? ""] ?? (grant["source_type"] as? String ?? "").capitalized, systemImage: "checkmark.circle")
                            Spacer()
                            Button("Stop reading this", role: .destructive) { Task { await model.withdraw(grant["grant_id"] as? String ?? "") } }
                        }
                    }
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
