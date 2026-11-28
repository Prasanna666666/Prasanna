import AtlasKit
import SwiftUI

/// The reusable components of UI/UX specification section 5. Each has an accessibility label; status always carries a symbol and a word, never colour alone.

struct PageHeader: View {
    let title: String
    var subtitle: String?
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        VStack(alignment: .leading, spacing: Space.xs) {
            Text(title).font(TextStyle.title).foregroundStyle(theme.textPrimary).accessibilityAddTraits(.isHeader)
            if let subtitle { Text(subtitle).font(TextStyle.secondary).foregroundStyle(theme.textSecondary) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Empty, loading, unavailable, denied, partial and error states: one component, so no screen shows a blank panel.
struct StateNotice: View {
    enum Style { case info, loading, warning, problem }
    let text: String
    var style: Style = .info
    var actionTitle: String?
    var action: (() -> Void)?
    @Environment(\.colorScheme) private var scheme

    private var symbol: String {
        switch style {
        case .info: return "info.circle"
        case .loading: return "hourglass"
        case .warning: return "exclamationmark.triangle"
        case .problem: return "xmark.octagon"
        }
    }

    var body: some View {
        let theme = Theme(scheme)
        let tint: Color = style == .problem ? theme.destructive : (style == .warning ? theme.warning : theme.textSecondary)
        HStack(alignment: .top, spacing: Space.md) {
            if style == .loading { ProgressView().controlSize(.small) } else { Image(systemName: symbol).foregroundStyle(tint).accessibilityHidden(true) }
            VStack(alignment: .leading, spacing: Space.sm) {
                Text(text).font(TextStyle.body).foregroundStyle(theme.textPrimary).fixedSize(horizontal: false, vertical: true)
                if let actionTitle, let action { Button(actionTitle, action: action) }
            }
            Spacer(minLength: 0)
        }
        .padding(Space.md)
        .background(theme.surface, in: RoundedRectangle(cornerRadius: Radius.medium))
        .accessibilityElement(children: .combine)
    }
}

/// The task's status: symbol and words together.
struct PhaseLabel: View {
    let phase: TaskPhase
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        Label(phase.label, systemImage: phase.symbol)
            .font(TextStyle.secondary)
            .foregroundStyle(phase == .failed || phase == .expired ? theme.destructive : (phase == .completedWithLimitations ? theme.warning : theme.textSecondary))
            .accessibilityLabel("Status: \(phase.label)")
    }
}

struct CitationChip: View {
    let label: String
    let action: () -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        Button(action: action) { Label(label, systemImage: "text.quote").font(TextStyle.caption) }
            .buttonStyle(.bordered)
            .tint(theme.accent)
            .accessibilityLabel("Show evidence: \(label)")
            .help("Show the passage this answer relies on")
    }
}

/// The evidence inspector: the exact passage, its place in human words, and what is not known.
struct EvidenceInspector: View {
    let citation: CitationView?
    let state: EvidenceState?
    let close: () -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        VStack(alignment: .leading, spacing: Space.md) {
            HStack {
                Text("Evidence").font(TextStyle.headline).accessibilityAddTraits(.isHeader)
                Spacer()
                Button("Close", action: close).keyboardShortcut(.cancelAction)
            }
            if let citation { Text(citation.label).font(TextStyle.secondary).foregroundStyle(theme.textSecondary) }
            switch state {
            case .available(let text)?:
                ScrollView { Text(text).font(TextStyle.body).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                    .padding(Space.md).background(theme.surface, in: RoundedRectangle(cornerRadius: Radius.small))
            case let other?:
                StateNotice(text: other.message ?? UnavailableReason.unknownState.message, style: .warning)
            case nil:
                StateNotice(text: "Loading the passage.", style: .loading)
            }
            Spacer(minLength: 0)
        }
        .padding(Space.lg)
        .frame(minWidth: 280)
    }
}

struct ActivityRow: View {
    let item: ActivityItem
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        HStack(alignment: .top, spacing: Space.md) {
            Image(systemName: item.symbol).foregroundStyle(item.needsAttention ? theme.warning : theme.textSecondary).frame(width: 24).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Space.xs) {
                Text(item.title).font(TextStyle.body).foregroundStyle(theme.textPrimary)
                if !item.detail.isEmpty { Text(item.detail).font(TextStyle.secondary).foregroundStyle(theme.textSecondary) }
                Text(item.date, style: .relative).font(TextStyle.caption).foregroundStyle(theme.textMuted)
            }
            Spacer(minLength: 0)
            if item.needsAttention { Label("Needs your attention", systemImage: "exclamationmark.circle").font(TextStyle.caption).foregroundStyle(theme.warning) }
        }
        .padding(.vertical, Space.sm)
        .accessibilityElement(children: .combine)
    }
}

/// The exact action, destination and payload, with Approve and Decline. Approve is never the default button, and nothing is approved by Return alone.
struct ApprovalSheet: View {
    let flow: ApprovalFlow
    let approve: () -> Void
    let decline: () -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let theme = Theme(scheme)
        VStack(alignment: .leading, spacing: Space.lg) {
            Text("Approve this action?").font(TextStyle.title).accessibilityAddTraits(.isHeader)
            Text(flow.summary.title).font(TextStyle.headline)
            VStack(alignment: .leading, spacing: Space.sm) {
                ForEach(flow.summary.rows, id: \.label) { row in
                    HStack(alignment: .top) {
                        Text(row.label).foregroundStyle(theme.textSecondary).frame(width: 120, alignment: .leading)
                        Text(row.value).textSelection(.enabled)
                    }.font(TextStyle.body).accessibilityElement(children: .combine)
                }
            }
            .padding(Space.md).background(theme.surface, in: RoundedRectangle(cornerRadius: Radius.small))
            Label(flow.summary.consequence, systemImage: "exclamationmark.triangle").foregroundStyle(theme.warning).font(TextStyle.body)
            switch flow.state {
            case .pending:
                HStack {
                    Button("Decline", action: decline).keyboardShortcut(.cancelAction)
                    Spacer()
                    Button("Approve", action: approve).disabled(!flow.canApprove(now: Date()))
                }
            case .invalidated: StateNotice(text: "The details changed, so this approval no longer applies. Atlas will ask again.", style: .warning)
            case .expired: StateNotice(text: "This approval ran out of time. Atlas will ask again if you still want it.", style: .warning)
            case .approved: StateNotice(text: "Approved. Doing it now.", style: .loading)
            case .declined: StateNotice(text: "Declined. Nothing was done.")
            case .completed: StateNotice(text: "Done.")
            case .failed(let message): StateNotice(text: message, style: .problem)
            }
        }
        .padding(Space.xl)
        .frame(minWidth: 460)
    }
}
