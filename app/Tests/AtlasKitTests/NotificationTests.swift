import XCTest
@testable import AtlasKit

final class NotificationTests: XCTestCase {
    private func attention(_ key: String, _ t: TimeInterval = 1) -> ActivityItem {
        ActivityItem(id: "a-" + key, kind: .risk, title: "Two events overlap", detail: "“Dentist” overlaps “Team call”", date: Date(timeIntervalSince1970: t), needsAttention: true, dedupeKey: key)
    }

    func testNothingIsNotifiedUnlessTheOwnerTurnedNotificationsOn() {
        XCTAssertTrue(NotificationPlanner.plans(for: [attention("k1")], alreadyNotified: [], enabled: false).isEmpty)
        XCTAssertEqual(NotificationPlanner.plans(for: [attention("k1")], alreadyNotified: [], enabled: true).count, 1)
    }

    func testANotificationCarriesNoPrivateContent() {
        let plan = NotificationPlanner.plans(for: [attention("k1")], alreadyNotified: [], enabled: true)[0]
        XCTAssertEqual(plan.title, "Atlas")
        XCTAssertFalse(plan.body.contains("Dentist"))
        XCTAssertFalse(plan.body.contains("Team call"))
        XCTAssertEqual(plan.body, NotificationPlanner.genericBody)
    }

    func testAnEventIsNotifiedOnceAndOnlyMaterialItemsCount() {
        let plans = NotificationPlanner.plans(for: [attention("k1"), attention("k1", 5)], alreadyNotified: [], enabled: true)
        XCTAssertEqual(plans.map { $0.id }, ["k1"])
        XCTAssertTrue(NotificationPlanner.plans(for: [attention("k1")], alreadyNotified: ["k1"], enabled: true).isEmpty)
        let routine = ActivityItem(id: "t", kind: .task, title: "q", detail: "", date: Date(), needsAttention: false)
        XCTAssertTrue(NotificationPlanner.plans(for: [routine], alreadyNotified: [], enabled: true).isEmpty)
    }

    func testABurstIsLimitedSoAtlasNeverBecomesNoisy() {
        let many = (1...10).map { attention("k\($0)", TimeInterval($0)) }
        XCTAssertEqual(NotificationPlanner.plans(for: many, alreadyNotified: [], enabled: true).count, NotificationPlanner.maxPerRound)
    }
}
