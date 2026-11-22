import XCTest
@testable import AtlasKit

final class SubmissionGateTests: XCTestCase {
    func testASecondSubmissionWhileOneRunsIsRefusedAndTheFirstIsNotDisturbed() {
        var gate = SubmissionGate()
        XCTAssertTrue(gate.begin())
        for _ in 0..<5 { XCTAssertFalse(gate.begin(), "rapid repeated Enter must not start another task") }
        XCTAssertTrue(gate.busy)
    }

    func testTheGateReopensWhenTheQuestionEndsWhateverTheOutcome() {
        var gate = SubmissionGate()
        XCTAssertTrue(gate.begin())
        gate.end()
        XCTAssertFalse(gate.busy)
        XCTAssertTrue(gate.begin())
    }

    func testCancellationTargetsTheOnlyRunningTask() {
        // The model keeps one task id; because a second begin() is refused, the id cannot be overwritten while the first runs.
        var gate = SubmissionGate()
        var taskID: String?
        if gate.begin() { taskID = "first" }
        if gate.begin() { taskID = "second" }
        XCTAssertEqual(taskID, "first")
    }
}
