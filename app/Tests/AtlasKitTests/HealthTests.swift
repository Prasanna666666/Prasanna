import XCTest
@testable import AtlasKit

final class HealthTests: XCTestCase {
    private let ready: [String: Any] = [
        "state": "ready", "reading_count": 3, "computed_by_code": true,
        "measures": [[
            "measure": "weight", "unit": "kg", "count": 3,
            "latest": ["date": "2026-10-15", "value": "71.2", "basis": "estimated"],
            "minimum": "70.0", "maximum": "71.2", "average": "70.57", "average_is_rounded": true,
            "bases": ["measured": 2, "estimated": 1, "unlabelled": 0],
        ]],
    ]

    func testReadingsAreShownExactlyWithTheirBasisAndTheAverageIsLabelledRounded() {
        guard case .loaded(let view) = HealthOutcome.from(ready) else { return XCTFail("expected a summary") }
        let m = view.measures[0]
        XCTAssertEqual(m.title, "Weight")
        XCTAssertEqual(m.latestLine, "Latest: 71.2 kg on 2026-10-15 (estimated).")
        XCTAssertEqual(m.rangeLine, "Lowest 70.0 kg, highest 71.2 kg, from 3 readings.")
        XCTAssertEqual(m.averageLine, "Average 70.57 kg (rounded).")
        XCTAssertEqual(m.basisLine, "2 measured, 1 estimated")
        XCTAssertTrue(view.basis.contains("not medical advice"))
    }

    func testAnUnlabelledReadingIsNeverShownAsMeasured() {
        var response = ready
        response["measures"] = [[
            "measure": "weight", "unit": "lb", "count": 1,
            "latest": ["date": "2026-10-16", "value": "155", "basis": "unlabelled"],
            "minimum": "155", "maximum": "155", "average": "155.00", "average_is_rounded": true,
            "bases": ["measured": 0, "estimated": 0, "unlabelled": 1],
        ]]
        guard case .loaded(let view) = HealthOutcome.from(response) else { return XCTFail() }
        XCTAssertTrue(view.measures[0].latestLine.hasSuffix("(not labelled)."))
        XCTAssertEqual(view.measures[0].basisLine, "1 not labelled")
        XCTAssertTrue(view.measures[0].rangeLine.contains("1 reading."))
    }

    func testOffEmptyAndUnknownStatesAreDifferentAndNeverBlank() {
        guard case .denied(let text) = HealthOutcome.from(["state": "denied"]) else { return XCTFail() }
        XCTAssertTrue(text.contains("Turn it on in Settings"))
        XCTAssertNotNil(HealthOutcome.from(["state": "empty"]).notice)
        guard case .unavailable(.unknownState) = HealthOutcome.from(["state": "whatever"]) else { return XCTFail() }
        guard case .unavailable(.unknownState) = HealthOutcome.from(["state": "ready", "measures": []]) else { return XCTFail() }  // ready without figures fails safe
    }
}
