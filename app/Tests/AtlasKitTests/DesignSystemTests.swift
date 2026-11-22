import XCTest
@testable import AtlasKit

/// The design tokens: legible in both appearances, on a consistent grid, complete.
final class DesignSystemTests: XCTestCase {
    func testEveryTextColourIsLegibleOnTheBackgroundAndTheSurfaceInBothAppearances() {
        for appearance in Appearance.allCases {
            let colours = Tokens.colors(appearance)
            for text in colours.textColours {
                XCTAssertGreaterThanOrEqual(RGB.contrast(text, colours.background), 4.5, "\(appearance)")
                XCTAssertGreaterThanOrEqual(RGB.contrast(text, colours.surface), 4.5, "\(appearance)")
            }
        }
    }

    func testStatusAndAccentColoursReachContrastAndTheTextOnAccentIsLegible() {
        for appearance in Appearance.allCases {
            let colours = Tokens.colors(appearance)
            for signal in colours.signalColours { XCTAssertGreaterThanOrEqual(RGB.contrast(signal, colours.background), 4.5, "\(appearance)") }
            XCTAssertGreaterThanOrEqual(RGB.contrast(colours.onAccent, colours.accent), 4.5, "\(appearance)")
            XCTAssertGreaterThan(RGB.contrast(colours.separator, colours.background), 1.3)
        }
    }

    func testTextIsClearlyOrderedFromPrimaryToMuted() {
        for appearance in Appearance.allCases {
            let c = Tokens.colors(appearance)
            XCTAssertGreaterThan(RGB.contrast(c.textPrimary, c.background), RGB.contrast(c.textSecondary, c.background))
            XCTAssertGreaterThan(RGB.contrast(c.textSecondary, c.background), RGB.contrast(c.textMuted, c.background))
        }
    }

    func testContrastMathMatchesTheWCAGDefinition() {
        XCTAssertEqual(RGB.contrast(RGB(hex: 0xFFFFFF), RGB(hex: 0x000000)), 21, accuracy: 0.01)
        XCTAssertEqual(RGB.contrast(RGB(hex: 0x777777), RGB(hex: 0x777777)), 1, accuracy: 0.001)
    }

    func testSpacingIsOnAFourPointGridAndTypeAndRadiiAreOrdered() {
        for value in Tokens.Space.all where value >= 4 { XCTAssertEqual(value.truncatingRemainder(dividingBy: 4), 0) }
        XCTAssertEqual(Tokens.Space.all, Tokens.Space.all.sorted())
        XCTAssertEqual(Tokens.TypeScale.ordered, Tokens.TypeScale.ordered.sorted())
        XCTAssertLessThan(Tokens.Radius.small, Tokens.Radius.medium)
        XCTAssertLessThan(Tokens.Radius.medium, Tokens.Radius.large)
        XCTAssertGreaterThanOrEqual(Tokens.Size.minimumHit, 24)
        XCTAssertGreaterThanOrEqual(Tokens.TypeScale.body, 14)  // body text is sized for sustained reading
    }

    func testMotionIsShortAndOffWhenTheSystemAsksForReducedMotion() {
        XCTAssertLessThanOrEqual(Tokens.Motion.standard, 0.3)
        XCTAssertEqual(Tokens.Motion.duration(Tokens.Motion.standard, reduceMotion: true), 0)
        XCTAssertEqual(Tokens.Motion.duration(Tokens.Motion.standard, reduceMotion: false), Tokens.Motion.standard)
    }
}

final class NavigationTests: XCTestCase {
    func testOnlyAvailableDestinationsAreListedAndTheOrderIsFixed() {
        XCTAssertEqual(Sidebar.destinations(Availability()), [.home, .ask, .activity, .settings])
        let more = Sidebar.destinations(Availability(library: true, lifeAreas: ["Travel", "Finance"]))
        XCTAssertEqual(more, [.home, .ask, .library, .lifeArea("Finance"), .lifeArea("Travel"), .activity, .settings])
    }

    func testTheSelectionIsRestoredOnlyIfItIsStillAvailable() {
        let none = Availability()
        XCTAssertEqual(Sidebar.restored("settings", in: none), .settings)
        XCTAssertEqual(Sidebar.restored("library", in: none), .home)  // not available: falls back to Home
        XCTAssertEqual(Sidebar.restored(nil, in: none), .home)
        XCTAssertEqual(Sidebar.restored("life:Finance", in: Availability(lifeAreas: ["Finance"])), .lifeArea("Finance"))
        XCTAssertEqual(Sidebar.restored("garbage", in: none), .home)
    }

    func testRestorationKeysRoundTrip() {
        for destination in [Destination.home, .ask, .library, .lifeArea("Finance"), .activity, .settings] {
            XCTAssertEqual(Destination(restorationKey: destination.restorationKey), destination)
        }
        XCTAssertNil(Destination(restorationKey: "life:"))
    }

    func testTheShortcutsFollowTheListedOrderAndIgnoreNumbersWithNoDestination() {
        let list = Availability()
        XCTAssertEqual(Sidebar.destination(forShortcut: 1, in: list), .home)
        XCTAssertEqual(Sidebar.destination(forShortcut: 4, in: list), .settings)
        XCTAssertNil(Sidebar.destination(forShortcut: 5, in: list))
        XCTAssertNil(Sidebar.destination(forShortcut: 0, in: list))
    }

    func testTheLayoutCollapsesTheInspectorBeforeTheSidebarAndEveryDestinationHasALabelAndASymbol() {
        XCTAssertEqual(NavigationLayout.forWidth(500), .compact)
        XCTAssertEqual(NavigationLayout.forWidth(900), .medium)
        XCTAssertEqual(NavigationLayout.forWidth(1400), .wide)
        XCTAssertTrue(NavigationLayout.wide.inspectorIsTrailingColumn)
        XCTAssertFalse(NavigationLayout.medium.inspectorIsTrailingColumn)
        XCTAssertFalse(NavigationLayout.medium.sidebarIsCompact)
        XCTAssertTrue(NavigationLayout.compact.sidebarIsCompact)
        for destination in Sidebar.destinations(Availability(library: true, lifeAreas: ["Finance"])) {
            XCTAssertFalse(destination.title.isEmpty)
            XCTAssertFalse(destination.symbol.isEmpty)
        }
    }
}

final class LifecycleTests: XCTestCase {
    func testEveryCoreStateMapsToAPlainPhaseAndAnUnknownOneFailsSafely() {
        let known = ["requested", "policy_checked", "queued", "running", "retrieved", "drafted", "verified", "completed", "partially_completed", "failed", "cancelled", "expired"]
        for state in known { XCTAssertNotEqual(TaskPhase.from(coreState: state), .unknown, state) }
        XCTAssertEqual(TaskPhase.from(coreState: "something_new"), .unknown)
        XCTAssertEqual(TaskPhase.unknown.label, "Atlas cannot show this state")
    }

    func testCancelIsOfferedOnlyWhileWorkIsGoingOn() {
        XCTAssertTrue(TaskPhase.working.canCancel)
        XCTAssertTrue(TaskPhase.waiting.canCancel)
        for ended in [TaskPhase.completed, .completedWithLimitations, .failed, .cancelled, .expired, .unknown] { XCTAssertFalse(ended.canCancel) }
    }

    func testEveryPhaseHasALabelAndASymbolSoStatusNeverReliesOnColour() {
        let all: [TaskPhase] = [.received, .checkingAccess, .waiting, .working, .searching, .preparing, .checking, .completed, .completedWithLimitations, .failed, .cancelled, .expired, .unknown]
        for phase in all { XCTAssertFalse(phase.label.isEmpty); XCTAssertFalse(phase.symbol.isEmpty) }
        XCTAssertFalse(TaskPhase.working.label.contains("%"))  // no invented percentage
    }

    func testTheDisplayNeverMovesBackwardsAndACoalescedBurstShowsOnlyTheLatestForwardPhase() {
        var tracker = PhaseTracker()
        XCTAssertEqual(tracker.update(coreState: "requested"), .received)
        XCTAssertEqual(tracker.update(coreState: "running"), .working)
        XCTAssertNil(tracker.update(coreState: "queued"))  // an earlier phase: no flicker back
        XCTAssertNil(tracker.update(coreState: "running"))  // the same phase again: no change
        XCTAssertEqual(tracker.update(coreState: "verified"), .checking)  // skipping ahead is fine
        XCTAssertEqual(tracker.update(coreState: "partially_completed"), .completedWithLimitations)
        XCTAssertNil(tracker.update(coreState: "running"))  // nothing moves after the end
        XCTAssertEqual(tracker.shown, .completedWithLimitations)
    }

    func testTheConversationStateFollowsTheTaskAndKeepsAFailure() {
        XCTAssertEqual(ConversationState.from(phase: nil, composing: false, failure: nil), .empty)
        XCTAssertEqual(ConversationState.from(phase: nil, composing: true, failure: nil), .composing)
        XCTAssertEqual(ConversationState.from(phase: .received, composing: true, failure: nil), .submitted)
        XCTAssertEqual(ConversationState.from(phase: .searching, composing: false, failure: nil), .running(.searching))
        XCTAssertEqual(ConversationState.from(phase: .cancelled, composing: false, failure: nil), .finished(.cancelled))
        XCTAssertEqual(ConversationState.from(phase: .working, composing: false, failure: "x"), .failed("x"))
    }
}

final class ScreenStateTests: XCTestCase {
    func testEveryStateWithoutContentSaysWhy() {
        let states: [LoadState<Int>] = [.loading, .empty, .unavailable(.coreStarting), .unavailable(.coreUnreachable), .unavailable(.notAvailableYet), .unavailable(.unknownState), .denied("Atlas is not allowed to open this."), .failed("It failed.")]
        for state in states { XCTAssertNotNil(state.notice); XCTAssertFalse(state.hasContent) }
        XCTAssertNil(LoadState<Int>.loaded(1).notice)
        XCTAssertTrue(LoadState<Int>.partial(1, note: "Some sources were not available.").hasContent)
    }

    func testLaunchStatesSeparateASignInNeedFromAnUnreachableCore() {
        XCTAssertEqual(LaunchState.from(launchError: "Mac needs owner sign-in"), .needsOwnerSignIn)
        XCTAssertEqual(LaunchState.from(launchError: "the Core did not start"), .coreUnavailable(UnavailableReason.coreUnreachable.message))
        XCTAssertNil(LaunchState.ready.message)
        XCTAssertNotNil(LaunchState.startingCore.message)
    }

    func testEvidenceStatesNeverImplyASourceWasReadWhenItWasNot() {
        XCTAssertEqual(EvidenceState.from(coreCode: nil, text: "The total due is 1250.50 euro."), .available("The total due is 1250.50 euro."))
        XCTAssertEqual(EvidenceState.from(coreCode: nil, text: nil), .missing)
        XCTAssertEqual(EvidenceState.from(coreCode: "source_denied", text: nil), .sourceDenied)
        XCTAssertEqual(EvidenceState.from(coreCode: "conflict", text: nil), .stale)
        XCTAssertEqual(EvidenceState.from(coreCode: "weird", text: nil), .unsupportedLocator)
        for state in [EvidenceState.missing, .stale, .sourceDenied, .unsupportedLocator] { XCTAssertNotNil(state.message) }
        XCTAssertNil(EvidenceState.available("x").message)
    }
}

final class ApprovalTests: XCTestCase {
    private let payload: [String: Any] = ["to": "alex@example.invalid", "event": "e1"]

    private func flow(_ expires: TimeInterval = 600) -> ApprovalFlow {
        let summary = ApprovalDescriber.describe(approvalID: "0123456789abcdef", action: "calendar.send_invitation", payload: payload, category: 1)!
        return ApprovalFlow(summary: summary, expiresAt: Date(timeIntervalSince1970: expires))
    }

    func testTheSummaryShowsTheExactActionAndEveryPayloadFieldInPlainWords() {
        let summary = flow().summary
        XCTAssertEqual(summary.title, "Send a calendar invitation")
        XCTAssertEqual(summary.rows, [ApprovalRow(label: "Event", value: "e1"), ApprovalRow(label: "To", value: "alex@example.invalid")])
        XCTAssertEqual(summary.consequence, "This sends information outside your Mac.")
        XCTAssertEqual(summary.category, 1)
    }

    func testAnActionAtlasCannotDescribeIsNeverShownForApproval() {
        XCTAssertNil(ApprovalDescriber.describe(approvalID: "x", action: "mystery.action", payload: [:], category: 1))
        XCTAssertNil(ApprovalDescriber.describe(approvalID: "x", action: "calendar.send_invitation", payload: payload, category: 9))
    }

    func testApprovalNeedsADeliberateStepAndWorksOnceWhileValid() {
        var f = flow()
        XCTAssertEqual(f.state, .pending)
        XCTAssertTrue(f.canApprove(now: Date(timeIntervalSince1970: 0)))
        XCTAssertTrue(f.approved(now: Date(timeIntervalSince1970: 0)))
        XCTAssertEqual(f.state, .approved)
        XCTAssertFalse(f.approved(now: Date(timeIntervalSince1970: 1)))  // not twice
        f.finished(success: true, message: "")
        XCTAssertEqual(f.state, .completed)
    }

    func testAMaterialChangeInvalidatesTheApprovalAndAnUnchangedPayloadDoesNot() {
        var same = flow()
        same.payloadChanged(to: payload)
        XCTAssertEqual(same.state, .pending)
        var changed = flow()
        changed.payloadChanged(to: ["to": "someone-else@example.invalid", "event": "e1"])
        XCTAssertEqual(changed.state, .invalidated)
        XCTAssertFalse(changed.canApprove(now: Date(timeIntervalSince1970: 0)))
        var late = flow()
        _ = late.approved(now: Date(timeIntervalSince1970: 0))
        late.payloadChanged(to: ["to": "other@example.invalid", "event": "e1"])
        XCTAssertEqual(late.state, .invalidated)  // even after approval and before it runs
    }

    func testAnApprovalExpiresAndADeclineIsFinal() {
        var f = flow(10)
        XCTAssertFalse(f.canApprove(now: Date(timeIntervalSince1970: 11)))
        f.expireIfDue(now: Date(timeIntervalSince1970: 11))
        XCTAssertEqual(f.state, .expired)
        var g = flow()
        g.declined()
        XCTAssertEqual(g.state, .declined)
        XCTAssertFalse(g.approved(now: Date(timeIntervalSince1970: 0)))
        var h = flow()
        _ = h.approved(now: Date(timeIntervalSince1970: 0))
        h.finished(success: false, message: "The invitation could not be sent.")
        XCTAssertEqual(h.state, .failed("The invitation could not be sent."))
    }

    func testPayloadValuesAreRenderedExactlyAndDeterministically() {
        let summary = ApprovalDescriber.describe(approvalID: "x", action: "notes.erase", payload: ["id": "n1", "count": 3, "confirmed": true], category: 3)!
        XCTAssertEqual(summary.rows.map { $0.label }, ["Confirmed", "Count", "Id"])
        XCTAssertEqual(summary.rows.map { $0.value }, ["Yes", "3", "n1"])
    }
}

final class ActivityTests: XCTestCase {
    private func item(_ id: String, _ kind: ActivityItem.Kind, _ t: TimeInterval, attention: Bool = false, key: String? = nil) -> ActivityItem {
        ActivityItem(id: id, kind: kind, title: id, detail: "", date: Date(timeIntervalSince1970: t), needsAttention: attention, dedupeKey: key)
    }

    func testTheFeedIsNewestFirstAndOneItemPerEvent() {
        let merged = ActivityFeed.merged([item("a", .task, 1), item("b", .update, 3), item("c", .task, 2), item("note", .update, 5, key: "a"), item("a-older", .task, 0, key: "a")])
        XCTAssertEqual(merged.map { $0.id }, ["note", "b", "c"])
    }

    func testAttentionShowsOnlyMaterialItemsAndHidesWhenThereAreNone() {
        XCTAssertEqual(ActivityFeed.needingAttention([item("a", .task, 1), item("b", .risk, 2, attention: true)]).map { $0.id }, ["b"])
        XCTAssertTrue(ActivityFeed.needingAttention([item("a", .task, 1)]).isEmpty)
    }

    func testContinueWhereYouLeftOffIsASmallNumberOfRecentTasks() {
        let items = (1...6).map { item("t\($0)", .task, TimeInterval($0)) } + [item("u", .update, 100)]
        XCTAssertEqual(ActivityFeed.recentTasks(items).map { $0.id }, ["t6", "t5", "t4"])
    }

    func testTheGreetingNeedsALocalTimeAndEveryItemHasASymbol() {
        XCTAssertEqual(Greeting.text(hour: nil), "Your Atlas")
        XCTAssertEqual(Greeting.text(hour: 9), "Good morning")
        XCTAssertEqual(Greeting.text(hour: 14), "Good afternoon")
        XCTAssertEqual(Greeting.text(hour: 21), "Good evening")
        XCTAssertEqual(Greeting.text(hour: 40), "Your Atlas")
        for kind in [ActivityItem.Kind.task, .update, .risk, .decision, .action] { XCTAssertFalse(item("x", kind, 0).symbol.isEmpty) }
    }
}
