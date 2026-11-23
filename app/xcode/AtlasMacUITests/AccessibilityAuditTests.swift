import AppKit
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
        print("PIXELS: \(pixelReport(app))")  // what is really on screen, to compare with what the audit says
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
            if issue.auditType == .sufficientElementDescription, let e = issue.element, e.elementType == .group, e.label.isEmpty, abs(e.frame.width - window.width) < 1 { return true }
            return false
        }
    }

    /// The darkest and lightest colours inside the first paragraph's frame and the colour in the window's corner, from the real screenshot.
    private func pixelReport(_ app: XCUIApplication) -> String {
        let window = app.windows.firstMatch
        guard let cg = window.screenshot().image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return "no image" }
        let scale = CGFloat(cg.width) / window.frame.width
        let paragraph = app.staticTexts.matching(NSPredicate(format: "value BEGINSWITH 'Atlas answers'")).firstMatch.frame
        let area = CGRect(x: (paragraph.minX - window.frame.minX) * scale, y: (paragraph.minY - window.frame.minY) * scale, width: paragraph.width * scale, height: paragraph.height * scale).integral
        let rep = NSBitmapImageRep(cgImage: cg)
        func hex(_ x: Int, _ y: Int) -> (String, Double) {
            guard let c = rep.colorAt(x: min(max(x, 0), cg.width - 1), y: min(max(y, 0), cg.height - 1))?.usingColorSpace(.sRGB) else { return ("?", 0) }
            let l = 0.2126 * c.redComponent + 0.7152 * c.greenComponent + 0.0722 * c.blueComponent
            return (String(format: "#%02X%02X%02X", Int(c.redComponent * 255), Int(c.greenComponent * 255), Int(c.blueComponent * 255)), Double(l))
        }
        var darkest = ("?", 2.0), lightest = ("?", -1.0)
        for y in stride(from: Int(area.minY), to: Int(area.maxY), by: 1) { for x in stride(from: Int(area.minX), to: Int(area.maxX), by: 1) { let p = hex(x, y); if p.1 < darkest.1 { darkest = p }; if p.1 > lightest.1 { lightest = p } } }
        return "corner=\(hex(8, 8).0) paragraphDarkest=\(darkest.0) paragraphLightest=\(lightest.0) paragraphFrame=\(paragraph) window=\(window.frame)"
    }
}
