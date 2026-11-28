import XCTest
@testable import AtlasKit

final class LibraryTests: XCTestCase {
    private func result(_ id: String, _ title: String, type: String = "documents") -> [String: Any] {
        ["source_id": id, "source_type": type, "title": title, "excerpt": "The total due is 1250.50 euro.", "locator_kind": "block"]
    }

    func testResultsBecomeRowsWithATitleAKindAnExcerptAndAPlaceInWords() {
        let state = LibraryOutcome.from(["state": "results", "results": [result("a", "Invoice"), result("b", "Letter")], "coverage": [["source_type": "documents", "total": 5, "searched": 5, "complete": true]]])
        guard case .loaded(let page) = state else { return XCTFail("expected results") }
        XCTAssertEqual(page.results.map { $0.title }, ["Invoice", "Letter"])
        XCTAssertFalse(page.results[0].kind.isEmpty)
        XCTAssertFalse(page.results[0].place.contains("{"))
        XCTAssertEqual(page.coverageLine?.hasSuffix("read 5 of 5."), true)
        XCTAssertEqual(page.types, ["documents"])
    }

    func testNotFoundNotReadYetAndNotAllowedAreDifferentStatesWithDifferentWords() {
        XCTAssertNotNil(LibraryOutcome.from(["state": "no_results", "results": [], "coverage": []]).notice)
        let partial = LibraryOutcome.from(["state": "partial_no_results", "results": [], "coverage": [["source_type": "mail", "total": 10, "searched": 3, "complete": false]]])
        guard case .partial(let page, let note) = partial else { return XCTFail("expected partial") }
        XCTAssertTrue(page.results.isEmpty)
        XCTAssertTrue(note.contains("still reading"))
        XCTAssertTrue(note.contains("read 3 of 10"))  // an incomplete index is never shown as a complete search
        guard case .denied(let text) = LibraryOutcome.from(["state": "denied", "results": [], "coverage": []]) else { return XCTFail("expected denied") }
        XCTAssertTrue(text.contains("not allowed"))
    }

    func testAnUnknownStateFailsSafelyInsteadOfShowingRawText() {
        guard case .unavailable(let reason) = LibraryOutcome.from(["state": "something_new"]) else { return XCTFail("expected unavailable") }
        XCTAssertEqual(reason, .unknownState)
        guard case .unavailable = LibraryOutcome.from([:]) else { return XCTFail("expected unavailable") }
    }

    func testSortingIsExplicitAndStable() {
        let rows = ["b", "A", "c", "a"].enumerated().map { LibraryResult(id: "\($0.offset)", sourceType: "documents", kind: "", title: $0.element, excerpt: "", place: "") }
        XCTAssertEqual(LibrarySort.bestMatch.apply(rows).map { $0.title }, ["b", "A", "c", "a"])
        XCTAssertEqual(LibrarySort.title.apply(rows).map { $0.title }, ["A", "a", "b", "c"])  // case-insensitive, ties keep the Core's order
        XCTAssertEqual(LibrarySort.allCases.map { $0.rawValue }, ["Best match", "Title"])
    }

    func testRowsWithoutAnIdAreDroppedAndAMissingTitleFallsBackToTheKind() {
        let state = LibraryOutcome.from(["state": "results", "results": [["source_type": "documents", "title": "x"], ["source_id": "z", "source_type": "documents", "title": "", "excerpt": "", "locator_kind": "block"]], "coverage": []])
        guard case .loaded(let page) = state else { return XCTFail() }
        XCTAssertEqual(page.results.count, 1)
        XCTAssertFalse(page.results[0].title.isEmpty)
    }
}
