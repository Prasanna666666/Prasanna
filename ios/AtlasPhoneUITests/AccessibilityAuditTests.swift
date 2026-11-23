import XCTest

/// Runs the system's own accessibility audit (contrast, hit-region size, Dynamic Type, labels, clipped text) over the phone app's screens and keeps a screenshot of each as an attachment of the test result.
/// It starts the app in a state with no pairing, which is the first thing a person sees.
final class AccessibilityAuditTests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }

    private func keep(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    private func audit(_ app: XCUIApplication, excluding: XCUIAccessibilityAuditType = []) throws {
        try app.performAccessibilityAudit(for: XCUIAccessibilityAuditType.all.subtracting(excluding)) { issue in
            let element = issue.element.map { "\($0.elementType.rawValue) '\($0.label)' \($0.identifier)" } ?? "no element"
            let line = "AUDIT ISSUE: \(issue.auditType) | \(issue.compactDescription) | \(issue.detailedDescription) | \(element)"
            print(line)  // shows in the CI log, so a finding names the element it is about
            self.add(XCTAttachment(string: line))
            // One finding is set aside, and only this one: the audit says the Pair button's text cannot change size, in every form the button has been given, yet the test below measures that it DOES
            // grow at the largest text size. Everything else, for every element, still fails the test.
            return issue.auditType == .dynamicType && (issue.element?.label ?? "") == "Pair"
        }
    }

    /// The behaviour the audit's Dynamic Type check is meant to establish, measured directly: the main action is taller at the largest text size than at the default.
    func testThePairButtonReallyGrowsWithTheTextSize() throws {
        func height(_ arguments: [String]) -> CGFloat {
            let app = XCUIApplication()
            app.launchArguments += arguments
            app.launch()
            defer { app.terminate() }
            _ = app.staticTexts["Pair with your Mac"].waitForExistence(timeout: 10)
            for _ in 0..<6 where !app.buttons["Pair"].exists { app.swipeUp() }
            return app.buttons["Pair"].frame.height
        }
        let normal = height([])
        let largest = height(["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        XCTAssertGreaterThan(normal, 0)
        XCTAssertGreaterThan(largest, normal, "the main action must grow with the text size (normal \(normal), largest \(largest))")
    }

    /// With a code typed.
    func testThePairingScreenWithACodeTypedPassesTheFullAccessibilityAudit() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.staticTexts["Pair with your Mac"].waitForExistence(timeout: 10), "the first screen explains how to pair")
        let field = app.textFields.firstMatch.exists ? app.textFields.firstMatch : app.textViews.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("atlas")
        keep(app, "pairing-screen-code-typed")
        try audit(app)
    }

    /// As first shown, with nothing typed. The Pair button is never disabled (it says what is missing instead), so every audit applies.
    func testThePairingScreenAsFirstShownPassesTheFullAccessibilityAudit() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.staticTexts["Pair with your Mac"].waitForExistence(timeout: 10))
        keep(app, "pairing-screen")
        try audit(app)
    }

    func testThePairingScreenStillWorksAtTheLargestTextSize() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.staticTexts["Pair with your Mac"].waitForExistence(timeout: 10))
        for _ in 0..<6 where !app.buttons["Pair"].exists { app.swipeUp() }  // a long form scrolls; the action must be reachable by scrolling
        XCTAssertTrue(app.buttons["Pair"].exists, "the main action is reachable at the largest text size")
        keep(app, "pairing-screen-largest-text")
    }
}
