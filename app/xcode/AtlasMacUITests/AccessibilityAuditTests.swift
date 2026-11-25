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
        let welcome = app.staticTexts["Welcome to Atlas"]
        let homePrompt = app.staticTexts["Ask about your own documents and mail. Atlas answers on this Mac and shows where each answer comes from."]
        let isFirstRun = welcome.waitForExistence(timeout: 60)
        let isHome = isFirstRun ? false : homePrompt.waitForExistence(timeout: 30)
        XCTAssertTrue(isFirstRun || isHome, "the app reaches a stable, expected first-run or Home screen")
        let labels = app.staticTexts.allElementsBoundByIndex.map { $0.label }
        print("SCREEN TEXTS: \(labels)")
        add(XCTAttachment(string: "Screen texts: \(labels)"))
        print("TREE: \(app.debugDescription)")  // the accessibility tree in the CI log, to name any element a finding is about
        keep(app, "first-screen")
        try app.performAccessibilityAudit { issue in
            let element = issue.element.map { "\($0.elementType.rawValue) '\($0.label)' \($0.identifier)" } ?? "no element"
            let line = "AUDIT ISSUE: \(issue.auditType) | \(issue.compactDescription) | \(issue.detailedDescription) | \(element) | \(issue.element?.debugDescription ?? "")"
            print(line)  // shows in the CI log, so a finding names the element it is about
            self.add(XCTAttachment(string: line))
            // Set aside only the window's own structural root: an unlabelled group that fills the whole window and holds the content. SwiftUI gives an app no way to label it; every other element still must pass.
            let window = app.windows.firstMatch.frame
            if let e = issue.element { print("EXEMPTION CHECK: type=\(issue.auditType == .sufficientElementDescription) group=\(e.elementType == .group) emptyLabel=\(e.label.isEmpty) width=\(e.frame.width) window=\(window.width)") }

            // The system's own window controls (the red, yellow and green buttons) contain tiny groups that macOS itself reports as parent/child mismatches. They are not Atlas's: set aside only a group no larger than
            // 20 points that sits inside the title bar (the top 40 points of the window).
            if issue.auditType == .parentChild, let e = issue.element, e.elementType == .group, e.frame.width <= 20, e.frame.height <= 20, e.frame.minY - window.minY <= 40 { return true }
            // The Touch Bar is the system's, not the app's (it appears in the tree of any app on this machine).
            if let e = issue.element, e.elementType == .touchBar { return true }
            if issue.auditType == .sufficientElementDescription, let e = issue.element, e.elementType == .group, e.label.isEmpty, abs(e.frame.width - window.width) < 1 { return true }
            return false
        }
    }

}
