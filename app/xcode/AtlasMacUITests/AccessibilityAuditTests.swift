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
        sleep(8)  // the Core starts before the first real screen replaces "starting"
        let labels = app.staticTexts.allElementsBoundByIndex.map { $0.label }
        print("SCREEN TEXTS: \(labels)")  // so a CI log shows which screen was audited
        add(XCTAttachment(string: "Screen texts: \(labels)"))
        XCTAssertFalse(labels.isEmpty, "the first screen shows text")
        print("TREE: \(app.debugDescription)")  // the accessibility tree in the CI log, to name any element a finding is about
        keep(app, "first-screen")
        try app.performAccessibilityAudit { issue in
            let element = issue.element.map { "\($0.elementType.rawValue) '\($0.label)' \($0.identifier)" } ?? "no element"
            let line = "AUDIT ISSUE: \(issue.auditType) | \(issue.compactDescription) | \(issue.detailedDescription) | \(element) | \(issue.element?.debugDescription ?? "")"
            print(line)  // shows in the CI log, so a finding names the element it is about
            self.add(XCTAttachment(string: line))
            // Set aside only the window's own structural root: an unlabelled group that fills the whole window and holds the content. SwiftUI gives an app no way to label it; every other element still must pass.
            let window = app.windows.firstMatch.frame
            if issue.auditType == .sufficientElementDescription, let e = issue.element, e.elementType == .group, e.label.isEmpty, e.frame == window { return true }
            return false
        }
    }
}
