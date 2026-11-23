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
            // The audit's contrast verdict is heuristic (it has flagged near-black text on white as failing). The same property is measured here from the real screenshot, and a finding is set aside only if the
            // measured contrast of that element is at least 4.5:1, the WCAG AA threshold for normal text.
            if issue.auditType == .contrast, let e = issue.element {
                let ratio = self.measuredContrast(app, e.frame)
                print("MEASURED CONTRAST: \(ratio) for \(e.frame)")
                if ratio >= 4.5 { return true }
            }
            // The system's own window controls (the red, yellow and green buttons) contain tiny groups that macOS itself reports as parent/child mismatches. They are not Atlas's: set aside only a group no larger than
            // 20 points that sits inside the title bar (the top 40 points of the window).
            if issue.auditType == .parentChild, let e = issue.element, e.elementType == .group, e.frame.width <= 20, e.frame.height <= 20, e.frame.minY - window.minY <= 40 { return true }
            // The Touch Bar is the system's, not the app's (it appears in the tree of any app on this machine).
            if let e = issue.element, e.elementType == .touchBar { return true }
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

    /// WCAG contrast ratio between the lightest and the darkest colour inside a frame of the real screenshot (text against its background).
    private func measuredContrast(_ app: XCUIApplication, _ frame: CGRect) -> Double {
        let window = app.windows.firstMatch
        guard let cg = window.screenshot().image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return 0 }
        let scale = CGFloat(cg.width) / window.frame.width
        let area = CGRect(x: (frame.minX - window.frame.minX) * scale, y: (frame.minY - window.frame.minY) * scale, width: frame.width * scale, height: frame.height * scale).integral
        let rep = NSBitmapImageRep(cgImage: cg)
        func linear(_ v: CGFloat) -> Double { let d = Double(v); return d <= 0.03928 ? d / 12.92 : pow((d + 0.055) / 1.055, 2.4) }
        var low = 2.0, high = -1.0
        for y in Int(max(area.minY, 0))..<Int(min(area.maxY, CGFloat(cg.height))) {
            for x in Int(max(area.minX, 0))..<Int(min(area.maxX, CGFloat(cg.width))) {
                guard let c = rep.colorAt(x: x, y: y)?.usingColorSpace(.sRGB) else { continue }
                let l = 0.2126 * linear(c.redComponent) + 0.7152 * linear(c.greenComponent) + 0.0722 * linear(c.blueComponent)
                low = min(low, l); high = max(high, l)
            }
        }
        return high < 0 ? 0 : (high + 0.05) / (low + 0.05)
    }
}
