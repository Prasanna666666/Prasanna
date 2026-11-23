import AtlasKit
import SwiftUI

/// The app shell: launch states first, then Get Started once, then one sidebar and the selected destination (UI/UX specification sections 3 and 11).
struct RootView: View {
    @ObservedObject var model: AppModel
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Group {
            if let message = model.launch.message {
                LaunchView(message: message, showsRetry: model.launch != .startingCore) { Task { await model.retryLaunch() } }
            } else if model.needsGetStarted {
                GetStartedView(model: model)
            } else {
                Shell(model: model)
            }
        }
        .background(Theme(scheme).background)
        .sheet(item: approvalBinding) { _ in
            if let flow = model.approval {
                ApprovalSheet(flow: flow, approve: { Task { await model.approveCurrent() } }, decline: { model.declineCurrent() })
            }
        }
    }

    /// The sheet is bound to the approval's id so it appears and goes away with the approval.
    private var approvalBinding: Binding<ApprovalIdentity?> {
        Binding(get: { model.approval.map { ApprovalIdentity(id: $0.summary.approvalID) } }, set: { if $0 == nil { model.dismissApproval() } })
    }
}

struct ApprovalIdentity: Identifiable { let id: String }

struct LaunchView: View {
    let message: String
    let showsRetry: Bool
    let retry: () -> Void

    var body: some View {
        VStack(spacing: Space.lg) {
            StateNotice(text: message, style: showsRetry ? .warning : .loading, actionTitle: showsRetry ? "Try again" : nil, action: showsRetry ? retry : nil)
        }
        .padding(Space.xxl)
        .frame(maxWidth: Metrics.readingWidth)
    }
}

struct Shell: View {
    @ObservedObject var model: AppModel
    @State private var columns = NavigationSplitViewVisibility.automatic
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        GeometryReader { geometry in
            let layout = NavigationLayout.forWidth(Double(geometry.size.width))
            NavigationSplitView(columnVisibility: $columns) {
                List(Sidebar.destinations(model.availability), id: \.self, selection: Binding(get: { Optional(model.selection) }, set: { if let value = $0 { model.select(value) } })) { destination in
                    Label(destination.title, systemImage: destination.symbol).tag(destination)
                }
                .navigationSplitViewColumnWidth(min: 180, ideal: Metrics.sidebarWidth, max: 280)
                .accessibilityLabel("Navigation")
            } detail: {
                HStack(spacing: 0) {
                    detail.frame(maxWidth: .infinity, maxHeight: .infinity)
                    if layout.inspectorIsTrailingColumn, model.selectedCitation != nil {
                        Divider()
                        EvidenceInspector(citation: model.selectedCitation, state: model.evidence, close: model.closeEvidence).frame(width: Metrics.inspectorWidth)
                    }
                }
                .sheet(isPresented: Binding(get: { !layout.inspectorIsTrailingColumn && model.selectedCitation != nil }, set: { if !$0 { model.closeEvidence() } })) {
                    EvidenceInspector(citation: model.selectedCitation, state: model.evidence, close: model.closeEvidence).frame(minWidth: 420, minHeight: 320)
                }
            }
            .onChange(of: layout) { _, newLayout in columns = newLayout.sidebarIsCompact ? .detailOnly : .automatic }
        }
        .background(Theme(scheme).background)
    }

    @ViewBuilder private var detail: some View {
        switch model.selection {
        case .home: HomeView(model: model)
        case .ask: AskView(model: model)
        case .activity: ActivityView(model: model)
        case .settings: SettingsView(model: model)
        case .library: LibraryView(model: model)
        case .lifeArea(let name):
            if let domain = OwnDomain(areaTitle: name) { RecordsView(model: model, domain: domain) } else if name == SourceNames.title("finance") { FinanceAreaView(model: model) } else if name == SourceNames.title("health") { HealthAreaView(model: model) } else { StateNotice(text: UnavailableReason.notAvailableYet.message).padding(Space.xl) }
        }
    }
}
