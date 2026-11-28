import XCTest
@testable import AtlasKit

/// First-run consent is opt-in: nothing is enabled until the owner chooses it, and continuing with nothing is valid.
final class GetStartedTests: XCTestCase {
    func testTheDefaultChoiceEnablesNothing() {
        let choice = GetStartedChoice()
        XCTAssertFalse(choice.documents)
        XCTAssertFalse(choice.mail)
        XCTAssertEqual(choice.sources, [])
    }

    func testContinuingWithNothingSelectedIsValidAndMakesNoRequestSoNoGrantCanExist() {
        let none = GetStartedChoice()
        XCTAssertTrue(none.canContinue)
        XCTAssertNil(GetStartedFlow.request(for: none))
    }

    func testOneSourceEnablesOnlyThatSource() {
        XCTAssertEqual(GetStartedFlow.request(for: GetStartedChoice(documents: true)), ["documents"])
        XCTAssertEqual(GetStartedFlow.request(for: GetStartedChoice(mail: true)), ["mail"])
    }

    func testBothSourcesEnableBothInAFixedOrder() {
        XCTAssertEqual(GetStartedFlow.request(for: GetStartedChoice(documents: true, mail: true)), ["documents", "mail"])
    }

    func testGetStartedIsShownUntilCompletedOnceOrAGrantExistsAndIsNotShownAgainAfterAnEmptyChoice() {
        XCTAssertTrue(GetStartedFlow.needsGetStarted(completedOnce: false, activeGrants: 0))
        XCTAssertFalse(GetStartedFlow.needsGetStarted(completedOnce: true, activeGrants: 0))  // continued with nothing enabled
        XCTAssertFalse(GetStartedFlow.needsGetStarted(completedOnce: false, activeGrants: 1))
        XCTAssertFalse(GetStartedFlow.needsGetStarted(completedOnce: true, activeGrants: 2))
    }
}
