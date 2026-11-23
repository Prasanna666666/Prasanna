import XCTest

/// The system's accessibility audit over the Mac app's first screen, with a screenshot kept in the test result. The app starts its real Core from the Python named by `ATLAS_CI_PYTHON` (a development override;
/// the packaged app uses the Python inside it), so what is audited is the screen a new owner actually sees.
final class AccessibilityAuditTests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }

    private func keep(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testTheFirstScreenAPersonSeesPassesTheAccessibilityAudit() throws {
        let app = XCUIApplication()
        if let python = ProcessInfo.processInfo.environment["ATLAS_CI_PYTHON"] { app.launchEnvironment["ATLAS_CI_PYTHON"] = python }
        app.launch()
        let window = app.windows.firstMatch
        XCTAssertTrue(window.waitForExistence(timeout: 30), "the app shows a window")
        let started = app.staticTexts["Get started"].waitForExistence(timeout: 60) || app.buttons["Ask Atlas"].waitForExistence(timeout: 5) || app.staticTexts.matching(NSPredicate(format: "label CONTAINS[c] 'Atlas'")).firstMatch.exists
        XCTAssertTrue(started, "a first screen is shown")
        keep(app, "first-screen")
        try app.performAccessibilityAudit { issue in
            let element = issue.element.map { "\($0.elementType.rawValue) '\($0.label)' \($0.identifier)" } ?? "no element"
            let line = "AUDIT ISSUE: \(issue.auditType) | \(issue.compactDescription) | \(issue.detailedDescription) | \(element)"
            print(line)  // shows in the CI log, so a finding names the element it is about
            self.add(XCTAttachment(string: line))
            return false
        }
    }
}
