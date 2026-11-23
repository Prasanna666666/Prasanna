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

    func testThePairingScreenPassesTheAccessibilityAudit() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.staticTexts["Pair with your Mac"].waitForExistence(timeout: 10), "the first screen explains how to pair")
        keep(app, "pairing-screen")
        try app.performAccessibilityAudit()
    }

    func testThePairingScreenStillWorksAtTheLargestTextSize() throws {
        let app = XCUIApplication()
        app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        app.launch()
        XCTAssertTrue(app.staticTexts["Pair with your Mac"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["Pair"].exists, "the main action is still on screen at the largest text size")
        keep(app, "pairing-screen-largest-text")
    }
}
