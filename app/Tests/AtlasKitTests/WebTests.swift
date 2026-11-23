import XCTest
@testable import AtlasKit

final class WebTests: XCTestCase {
    func testAPageIsShownWithItsSourceAndAnUntrustedWarningAndInstructionLikeTextIsFlagged() {
        let response: [String: Any] = ["url": "https://hours.example.org/opening", "domain": "hours.example.org", "retrieved_at": "2026-11-23T09:00:00Z", "text": "Open Monday to Friday.", "truncated": false, "injection_flags": ["instruction_like_text"], "trust": "untrusted", "authority": "none"]
        let page = WebOutcome.page(response)
        XCTAssertEqual(page?.domain, "hours.example.org")
        XCTAssertTrue(page?.note.contains("never acts on what a page says") == true)
        XCTAssertEqual(page?.warnings, ["This page contains text that looks like instructions. Atlas does not follow it."])
        XCTAssertNil(WebOutcome.page([:]))
    }

    func testHostsAndAddressesAreCheckedInPlainWordsBeforeAnythingIsSent() {
        XCTAssertNotNil(WebOutcome.hosts(["hosts": []]).notice)
        guard case .loaded(let hosts) = WebOutcome.hosts(["hosts": ["a.example.org"]]) else { return XCTFail() }
        XCTAssertEqual(hosts, ["a.example.org"])
        XCTAssertNil(WebOutcome.hostProblem("Example.org "))
        XCTAssertNotNil(WebOutcome.hostProblem("https://example.org"))
        XCTAssertNotNil(WebOutcome.hostProblem("localhost"))
        XCTAssertEqual(WebOutcome.problem(address: "http://a.example.org/x", hosts: ["a.example.org"]), "Enter a page address that starts with https.")
        XCTAssertTrue(WebOutcome.problem(address: "https://b.example.org/x", hosts: ["a.example.org"])?.contains("Add b.example.org") == true)
        XCTAssertNil(WebOutcome.problem(address: "https://a.example.org/x", hosts: ["a.example.org"]))
        XCTAssertTrue(WebOutcome.message(forCoreCode: "timeout").contains("may not be installed"))
    }
}
