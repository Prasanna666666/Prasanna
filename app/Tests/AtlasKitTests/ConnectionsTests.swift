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

    func testTheMacOnlyListensOnAPrivateOrVPNAddress() {
        for good in ["127.0.0.1:8443", "10.0.0.5:9000", "192.168.1.20:8443", "172.16.4.4:8443", "169.254.1.1:8443", "100.64.0.5:8443", "100.127.1.1:8443"] { XCTAssertEqual(RelayBind.parse(good), good) }
        for bad in ["0.0.0.0:8443", "8.8.8.8:8443", "100.128.0.1:8443", "localhost:8443", "192.168.1.20", "192.168.1.20:80", "192.168.1.20:99999", "192.168.1:8443", "::1:8443", ""] { XCTAssertNil(RelayBind.parse(bad), bad) }
        XCTAssertTrue(ConnectDraft.isHomeNetwork("100.100.1.1") && ConnectDraft.isHomeNetwork("mac.tail1234.ts.net") && !ConnectDraft.isHomeNetwork("100.200.1.1"))
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
