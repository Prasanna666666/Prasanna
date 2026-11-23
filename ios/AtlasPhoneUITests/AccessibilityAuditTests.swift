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
        try app.performAccessibilityAudit { issue in
            let element = issue.element.map { "\($0.elementType.rawValue) '\($0.label)' \($0.identifier)" } ?? "no element"
            let line = "AUDIT ISSUE: \(issue.auditType) | \(issue.compactDescription) | \(issue.detailedDescription) | \(element)"
            print(line)  // shows in the CI log, so a finding names the element it is about
            self.add(XCTAttachment(string: line))
            return false  // nothing is ignored
        }
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
