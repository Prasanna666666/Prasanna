import XCTest
@testable import AtlasKit

final class FinanceTests: XCTestCase {
    private let ready: [String: Any] = [
        "state": "ready", "currency": "EUR", "transaction_count": 6, "computed_by_code": true,
        "months": [["month": "2026-09", "total": "150.30"], ["month": "2026-10", "total": "412.60"]],
        "latest": ["month": "2026-10", "total": "412.60", "categories": [["category": "rent", "total": "412.30"], ["category": "tea", "total": "0.30"]], "previous_total": "150.30", "delta": "262.30", "percent": "174.5"],
    ]

    func testTheSummaryIsShownExactlyAsTheCoreComputedItWithTheBasisStated() {
        guard case .loaded(let view) = FinanceOutcome.from(ready) else { return XCTFail("expected a summary") }
        XCTAssertEqual(view.monthTitle, "October 2026")
        XCTAssertEqual(view.total, "€412.60")
        XCTAssertEqual(view.categories, [FinanceView.Line(label: "rent", amount: "€412.30"), FinanceView.Line(label: "tea", amount: "€0.30")])
        XCTAssertEqual(view.months.map { $0.amount }, ["€150.30", "€412.60"])
        XCTAssertTrue(view.basis.contains("not account balances"))
        XCTAssertTrue(view.basis.contains("6 transactions"))
    }

    func testTheChangeIsLabelledAndTheRoundedPercentageSaysItIsRounded() {
        guard case .loaded(let view) = FinanceOutcome.from(ready) else { return XCTFail() }
        XCTAssertEqual(view.changeLine, "€262.30 more than the month before (€150.30). About 174.5% (rounded).")
        var fewer = ready
        fewer["latest"] = ["month": "2026-10", "total": "100.00", "categories": [], "previous_total": "150.30", "delta": "-50.30", "percent": "-33.5"]
        guard case .loaded(let down) = FinanceOutcome.from(fewer) else { return XCTFail() }
        XCTAssertEqual(down.changeLine, "€50.30 less than the month before (€150.30). About 33.5% (rounded).")
        var first = ready
        first["latest"] = ["month": "2026-10", "total": "100.00", "categories": [], "previous_total": NSNull(), "delta": NSNull(), "percent": NSNull()]
        guard case .loaded(let none) = FinanceOutcome.from(first) else { return XCTFail() }
        XCTAssertNil(none.changeLine)  // no earlier month: nothing is compared
    }

    func testOffEmptyAndUnknownStatesAreDifferentAndNeverBlank() {
        guard case .denied(let text) = FinanceOutcome.from(["state": "denied"]) else { return XCTFail() }
        XCTAssertTrue(text.contains("Turn it on in Settings"))
        XCTAssertNotNil(FinanceOutcome.from(["state": "empty"]).notice)
        guard case .unavailable(.unknownState) = FinanceOutcome.from(["state": "whatever"]) else { return XCTFail() }
        guard case .unavailable(.unknownState) = FinanceOutcome.from(["state": "ready"]) else { return XCTFail() }  // ready without figures fails safe
    }

    func testMonthsAndMoneyAreFormattedWithoutArithmetic() {
        XCTAssertEqual(FinanceOutcome.monthTitle("2026-01"), "January 2026")
        XCTAssertEqual(FinanceOutcome.monthTitle("2026-13"), "2026-13")
        XCTAssertEqual(FinanceOutcome.money("1250.50", currency: "EUR"), "€1250.50")
        XCTAssertEqual(FinanceOutcome.money("-3.00", currency: "USD"), "-USD 3.00")
    }

    func testSensitiveSourcesAreExplainedAndNamedInPlainWords() {
        XCTAssertTrue(SourceNames.isSensitive("finance"))
        XCTAssertTrue(SourceNames.isSensitive("health"))
        XCTAssertFalse(SourceNames.isSensitive("documents"))
        XCTAssertTrue(SourceNames.explanation("finance").hasPrefix("Sensitive."))
        XCTAssertEqual(SourceNames.title("photos"), "Photos")
        XCTAssertTrue(SourceNames.explanation("photos").contains("never the pictures"))
        XCTAssertEqual(SourceNames.title("mail"), "Mail")
        XCTAssertEqual(SourceNames.title("something_new"), "Something_new")
    }
}
