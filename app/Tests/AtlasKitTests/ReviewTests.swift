import XCTest
@testable import AtlasKit

final class ReviewTests: XCTestCase {
    private func response(_ status: String = "completed") -> [String: Any] {
        ["status": status, "computed_by_code": true, "tasks": [],
         "sections": [
            ["area": "calendar", "state": "ready", "summary": "1 event pair overlaps: “Dentist” overlaps “Team call”."],
            ["area": "finance", "state": "ready", "summary": "Spent 412.60 EUR in 2026-10, added up by code from 6 transactions."],
            ["area": "health", "state": "denied", "summary": "This area is off. Turn it on in Settings to include it."],
         ]]
    }

    func testEachAreaIsShownWithTheCoresOwnWordsAndAnOffAreaOffersToBeTurnedOn() {
        guard case .loaded(let view) = ReviewOutcome.from(response()) else { return XCTFail() }
        XCTAssertEqual(view.sections.map { $0.title }, ["Calendar", "Finance", "Health"])
        XCTAssertEqual(view.sections[1].summary, "Spent 412.60 EUR in 2026-10, added up by code from 6 transactions.")
        XCTAssertEqual(view.sections.map { $0.needsAction }, [false, false, true])
        XCTAssertNil(view.note)
    }

    func testTheHighlightsSectionCarriesItsTaskAndIsNeverOfferedToBeTurnedOn() {
        var data = response()
        data["sections"] = [["area": "highlights", "state": "ready", "summary": "A summary is being written.", "task_id": "task-12345678"], ["area": "highlights", "state": "denied", "summary": "This area is off."]]
        guard case .loaded(let view) = ReviewOutcome.from(data) else { return XCTFail() }
        XCTAssertEqual(view.sections[0].title, "Highlights")
        XCTAssertEqual(view.sections[0].taskID, "task-12345678")
        XCTAssertFalse(view.sections[1].needsAction)  // Highlights uses whatever sources are on; it has no switch of its own
    }

    func testAnIncompleteReviewSaysSoAndAnUnreadableOneFailsSafe() {
        guard case .loaded(let partial) = ReviewOutcome.from(response("partially_completed")) else { return XCTFail() }
        XCTAssertNotNil(partial.note)
        guard case .unavailable(.unknownState) = ReviewOutcome.from([:]) else { return XCTFail() }
        guard case .unavailable(.unknownState) = ReviewOutcome.from(["status": "completed", "sections": []]) else { return XCTFail() }
    }
}
