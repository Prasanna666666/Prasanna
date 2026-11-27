import AppKit
import XCTest

/// The system's accessibility audit over the Mac app's first screen, with a screenshot kept in the test result. The app starts its real Core from the Python named by `ATLAS_CI_PYTHON` (a development override;
/// the packaged app uses the Python inside it), so what is audited is the screen a new owner actually sees.
final class AccessibilityAuditTests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }

    /// What the flagged element actually rendered: the lightest and darkest pixels in its own screenshot, and their WCAG contrast ratio. The
    /// log carries it, so a contrast finding can be diagnosed from evidence rather than from the source colours.
    static func measuredContrast(_ image: NSImage) -> String {
        guard let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil), let data = cg.dataProvider?.data, let bytes = CFDataGetBytePtr(data) else { return "no pixels" }
        let bpp = cg.bitsPerPixel / 8, row = cg.bytesPerRow
        func lum(_ c: Double) -> Double { let v = c / 255; return v <= 0.03928 ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4) }
        var lo = (l: 2.0, rgb: "?"), hi = (l: -1.0, rgb: "?"), counts: [String: Int] = [:]
        for y in stride(from: 0, to: cg.height, by: 2) {
            for x in stride(from: 0, to: cg.width, by: 2) {
                let o = y * row + x * bpp
                let (r, g, b) = (Double(bytes[o + 2]), Double(bytes[o + 1]), Double(bytes[o]))  // BGRA assumed (the macOS screenshot layout); a swapped order shifts luminance slightly but not the ratio's order of magnitude
                let l = 0.2126 * lum(r) + 0.7152 * lum(g) + 0.0722 * lum(b)
                let hex = String(format: "#%02X%02X%02X", Int(r), Int(g), Int(b))
                counts[hex, default: 0] += 1
                if l < lo.l { lo = (l, hex) }
                if l > hi.l { hi = (l, hex) }
            }
        }
        let ratio = (hi.l + 0.05) / (lo.l + 0.05)
        let common = counts.sorted { $0.value > $1.value }.prefix(4).map { "\($0.key)×\($0.value)" }.joined(separator: " ")
        return String(format: "darkest %@, lightest %@, ratio %.2f:1; most common %@ (size %dx%d, %d bpp)", lo.rgb, hi.rgb, ratio, common, cg.width, cg.height, cg.bitsPerPixel)
    }

    private func keep(_ app: XCUIApplication, _ name: String) {
        let shot = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    func testTheFirstScreenAPersonSeesPassesTheAccessibilityAudit() throws { try audit(appearance: "Light") }

    /// The same audit in Dark appearance, so a contrast finding can be attributed to one appearance or both (architect review: check both).
    func testTheFirstScreenPassesTheAccessibilityAuditInDarkAppearance() throws { try audit(appearance: "Dark") }

    private func audit(appearance: String) throws {
        let app = XCUIApplication()
        if let python = ProcessInfo.processInfo.environment["ATLAS_CI_PYTHON"] { app.launchEnvironment["ATLAS_CI_PYTHON"] = python }
        app.launchEnvironment["ATLAS_UI_TEST_APPEARANCE"] = appearance  // a test-scoped seam: the app sets NSApp.appearance from it (the launch argument was ignored)
        print("AUDIT APPEARANCE requested: \(appearance)")
        app.launch()
        app.activate()  // audited as the active, key window, so an inactive-window rendering is not what is measured
        let window = app.windows.firstMatch
        XCTAssertTrue(window.waitForExistence(timeout: 30), "the app shows a window")
        let welcome = app.staticTexts["Welcome to Atlas"]
        let homePrompt = app.staticTexts["Ask about your own documents and mail. Atlas answers on this Mac and shows where each answer comes from."]
        let isFirstRun = welcome.waitForExistence(timeout: 60)
        let isHome = isFirstRun ? false : homePrompt.waitForExistence(timeout: 30)
        XCTAssertTrue(isFirstRun || isHome, "the app reaches a stable, expected first-run or Home screen")
        if isFirstRun {  // the app reports its effective appearance on the first-run screen: the audit runs only in the one requested
            let effective = app.descendants(matching: .any)["get-started-\(appearance.lowercased())"]
            XCTAssertTrue(effective.waitForExistence(timeout: 10), "the app renders in the requested \(appearance) appearance")
            print("AUDIT APPEARANCE effective: \(effective.exists ? appearance : "not \(appearance)")")
        }
        let labels = app.staticTexts.allElementsBoundByIndex.map { $0.label }
        print("SCREEN TEXTS: \(labels)")
        add(XCTAttachment(string: "Screen texts: \(labels)"))
        print("TREE: \(app.debugDescription)")  // the accessibility tree in the CI log, to name any element a finding is about
        keep(app, "first-screen-\(appearance)")
        try app.performAccessibilityAudit { issue in
            let element = issue.element.map { "\($0.elementType.rawValue) '\($0.label)' \($0.identifier)" } ?? "no element"
            let line = "AUDIT ISSUE [\(appearance)]: \(issue.auditType) | \(issue.compactDescription) | \(issue.detailedDescription) | \(element) | \(issue.element?.debugDescription ?? "")"
            print(line)  // shows in the CI log, so a finding names the element it is about
            self.add(XCTAttachment(string: line))
            // A capture taken at the moment of the finding (not before the audit), so the reviewer sees what the audit measured.
            let atFinding = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
            atFinding.name = "at-audit-\(appearance)-\(issue.auditType.rawValue)"
            atFinding.lifetime = .keepAlways
            self.add(atFinding)
            if issue.auditType == .contrast, let e = issue.element { print("CONTRAST PIXELS [\(appearance)]: \(Self.measuredContrast(e.screenshot().image))") }
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
