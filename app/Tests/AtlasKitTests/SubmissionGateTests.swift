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

final class SubmissionCancellationTests: XCTestCase {
    func testStopBeforeCoreReturnsTheNewTaskIDIsAppliedToThatTask() {
        var cancellation = SubmissionCancellation()
        cancellation.begin()
        XCTAssertNil(cancellation.request())
        XCTAssertTrue(cancellation.bind("new-task"))
        XCTAssertEqual(cancellation.taskID, "new-task")
        cancellation.end()
        XCTAssertNil(cancellation.taskID)
        XCTAssertFalse(cancellation.requested)
    }

    func testNewSubmissionNeverRetainsThePreviousTaskID() {
        var cancellation = SubmissionCancellation()
        cancellation.begin()
        XCTAssertFalse(cancellation.bind("first-task"))
        XCTAssertEqual(cancellation.request(), "first-task")
        cancellation.end()
        cancellation.begin()
        XCTAssertNil(cancellation.taskID)
        XCTAssertNil(cancellation.request())
        XCTAssertTrue(cancellation.bind("second-task"))
        XCTAssertEqual(cancellation.taskID, "second-task")
    }

    func testUndoOnlyClearsWhenCoreExplicitlyConfirmsDone() {
        XCTAssertTrue(UndoConfirmation.isConfirmed(["status": "done"]))
        XCTAssertFalse(UndoConfirmation.isConfirmed(["status": "failed"]))
        XCTAssertFalse(UndoConfirmation.isConfirmed([:]))
    }
}
