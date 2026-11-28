import XCTest
@testable import AtlasKit

/// MAC-20, the app model's withdrawal behaviour (AppModel delegates to these): results shown from a withdrawn source are cleared, answers that
/// cite it are replaced by a notice, results that come back after the withdrawal are discarded, and incomplete coverage is worded truthfully.
final class WithdrawalTests: XCTestCase {
    private func result(_ id: String, _ type: String) -> LibraryResult {
        LibraryResult(id: id, sourceType: type, kind: type, title: id, excerpt: "", place: "")
    }

    private func answer(citing types: [String], coverage: [String: Any]? = nil, notSearched: [[String: Any]] = []) -> AnswerView {
        var raw: [String: Any] = ["answer": "x", "citations": types.map { ["evidence": ["source_type": $0, "locator": ["kind": "span_only"]], "quote": "q"] }, "not_searched": notSearched]
        if let coverage { raw["coverage"] = coverage }
        return AnswerView(raw)
    }

    func testWithdrawingASourceClearsEveryShownResultFromItAndOnlyThose() {
        let page = LibraryPage(results: [result("d1", "documents"), result("m1", "mail"), result("d2", "documents")], coverageLine: nil)
        guard case .loaded(let kept) = Withdrawal.library(.loaded(page), withdrawn: ["mail"]) else { return XCTFail("still loaded") }
        XCTAssertEqual(kept.results.map(\.id), ["d1", "d2"])
        guard case .empty = Withdrawal.library(.loaded(page), withdrawn: ["mail", "documents"]) else { return XCTFail("nothing left is shown as empty") }
        guard case .partial(let partly, _) = Withdrawal.library(.partial(page, note: "n"), withdrawn: ["documents"]) else { return XCTFail("partial stays partial") }
        XCTAssertEqual(partly.results.map(\.id), ["m1"])
    }

    func testAnAnswerCitingAWithdrawnSourceIsTakenOffAndOneThatDoesNotStays() {
        XCTAssertTrue(Withdrawal.hides(answer(citing: ["mail", "documents"]), withdrawn: ["mail"]))
        XCTAssertFalse(Withdrawal.hides(answer(citing: ["documents"]), withdrawn: ["mail"]))
        XCTAssertFalse(Withdrawal.hides(answer(citing: ["mail"]), withdrawn: []))
    }

    func testAResultThatComesBackAfterTheWithdrawalIsDiscarded() {
        let generation = ResultGeneration()
        let before = generation.token()  // a search started
        generation.advance()  // the owner withdrew a source while it ran
        XCTAssertFalse(generation.isCurrent(before))  // its result is not shown
        XCTAssertTrue(generation.isCurrent(generation.token()))
    }

    func testIncompleteCoverageIsWordedTruthfullyAndUnsearchedSourcesAreNamed() {
        let view = answer(citing: ["documents"], coverage: ["state": "partial", "searched": 3, "total": 10], notSearched: [["source_type": "mail", "reason_code": "no_grant"]])
        XCTAssertEqual(view.coverageLine, "Searched part of what is in scope. Searched 3 of 10.")
        XCTAssertEqual(view.notSearched, ["Mail: You have not allowed Atlas to search this."])
        let indexing = answer(citing: [], coverage: ["state": "indexing", "searched": 2])
        XCTAssertEqual(indexing.coverageLine, "Still reading your sources; results may be incomplete. Searched 2.")
    }
}
