import XCTest
@testable import AtlasKit

final class ConnectionsTests: XCTestCase {
    private func row(_ state: String = "not_connected", problem: Any = NSNull()) -> [String: Any] {
        ["id": "home", "title": "Home and devices", "category": "home", "summary": "See the state of your devices.", "state": state, "problem": problem,
         "read_scopes": ["device_state", "energy"],
         "writes": [["name": "control_device", "title": "Turn devices on or off", "approval": "never"], ["name": "unlock_door", "title": "Unlock a door", "approval": "always"]],
         "offline": "Shows the last known state.", "retention": "Kept on this Mac only.", "failure": "A device that does not answer is reported as such.",
         "fields": [["name": "address", "secret": false], ["name": "token", "secret": true]]]
    }

    func testEachIntegrationIsShownWithWhatItReadsAndWhichChangesAskFirst() {
        guard case .loaded(let views) = ConnectionsOutcome.from(["connectors": [row()]]) else { return XCTFail() }
        let home = views[0]
        XCTAssertEqual(home.stateLine, "Not connected")
        XCTAssertEqual(home.reads, "Device state, energy")
        XCTAssertEqual(home.changes.map { $0.asksFirst }, [false, true])
        XCTAssertEqual(home.changes[0].approvalNote, "Atlas does this without asking, and you can undo it.")
        XCTAssertEqual(home.changes[1].approvalNote, "Atlas asks you first, every time.")
        XCTAssertFalse(home.isConnected)
    }

    func testAServiceThatDoesNotAnswerNeedsAttentionInPlainWordsAndNeverLooksConnected() {
        guard case .loaded(let views) = ConnectionsOutcome.from(["connectors": [row("needs_attention", problem: "unreachable")]]) else { return XCTFail() }
        XCTAssertEqual(views[0].stateLine, "Needs attention. The service did not answer.")
        XCTAssertTrue(views[0].isConnected)  // credentials exist, so it can be checked or disconnected
        XCTAssertEqual(ConnectionsOutcome.problem("unauthorised"), "The service did not accept the access token.")
        XCTAssertFalse(ConnectionsOutcome.problem(nil).contains("_"))
    }

    func testAnUnreadableAnswerFailsSafeAndAnEmptyCatalogueSaysSo() {
        guard case .unavailable(.unknownState) = ConnectionsOutcome.from([:]) else { return XCTFail() }
        XCTAssertNotNil(ConnectionsOutcome.from(["connectors": []]).notice)
    }

    func testTheConnectFormSaysWhatIsWrongAndAllowsPlainHttpOnlyOnTheHomeNetwork() {
        var draft = ConnectDraft()
        XCTAssertNotNil(draft.problem())
        draft.address = "hub.example.com"
        XCTAssertEqual(draft.problem(), "Enter the address of the service. It starts with https.")
        draft.address = "http://api.example.com"
        XCTAssertTrue(draft.problem()?.contains("home network") == true)
        draft.address = "https://api.example.com"
        XCTAssertEqual(draft.problem(), "Enter the access token the service gave you.")
        draft.token = "  secret  "
        XCTAssertNil(draft.problem())
        XCTAssertEqual(draft.fields, ["address": "https://api.example.com", "token": "secret"])
        for home in ["http://192.168.1.20", "http://10.0.0.5:8080", "http://172.20.1.1", "http://localhost:3000", "http://hub.local"] {
            draft.address = home
            XCTAssertNil(draft.problem(), home)
        }
        draft.address = "http://172.40.1.1"
        XCTAssertNotNil(draft.problem())
    }
}
