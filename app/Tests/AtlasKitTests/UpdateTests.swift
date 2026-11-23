import XCTest
@testable import AtlasKit

final class UpdateTests: XCTestCase {
    func testTheInstalledVersionAndRollbackAreShownAndAnUnmanagedInstallSaysSo() {
        guard case .loaded(let managed) = UpdateOutcome.status(["installed": "1.1.0", "can_roll_back": true]) else { return XCTFail() }
        XCTAssertEqual(managed.installedLine, "Atlas version 1.1.0. Your data is not changed by updates.")
        XCTAssertTrue(managed.canRollBack)
        guard case .loaded(let unmanaged) = UpdateOutcome.status(["installed": NSNull(), "can_roll_back": false]) else { return XCTFail() }
        XCTAssertEqual(unmanaged.installedLine, "This copy of Atlas is not installed through the updater.")
        guard case .unavailable(.unknownState) = UpdateOutcome.status([:]) else { return XCTFail() }  // a response without the facts fails safe
    }

    func testEveryRefusalIsExplainedInPlainWordsAndSaysNothingChanged() {
        let codes = ["bad_signature", "bad_manifest", "bad_version", "bad_artefact", "unsafe_artefact", "artefact_does_not_match_manifest", "not_newer", "version_already_on_disk", "unhealthy_rolled_back", "unhealthy_first_install", "nothing_to_roll_back_to", "bad_release_folder", "something_new"]
        for code in codes {
            let text = UpdateOutcome.refusal(code)
            XCTAssertFalse(text.contains("_"), "\(code) must not leak a code to the screen")
            XCTAssertFalse(text.isEmpty)
        }
        XCTAssertTrue(UpdateOutcome.refusal("bad_signature").contains("not signed"))
        XCTAssertTrue(UpdateOutcome.refusal("something_new").contains("Nothing was changed"))
    }

    func testAnInstallTellsTheOwnerToRestartAndARefusalIsNotASuccess() {
        let ok = UpdateOutcome.result(["installed": "1.2.0", "restart_needed": true])
        XCTAssertTrue(ok.succeeded)
        XCTAssertEqual(ok.message, "Atlas 1.2.0 is ready. Quit and reopen Atlas to use it.")
        let refused = UpdateOutcome.result(["installed": NSNull(), "restart_needed": false, "refused": "not_newer"])
        XCTAssertFalse(refused.succeeded)
        XCTAssertEqual(refused.message, "That update is not newer than the version you have.")
        XCTAssertFalse(UpdateOutcome.result([:]).succeeded)
    }
}
