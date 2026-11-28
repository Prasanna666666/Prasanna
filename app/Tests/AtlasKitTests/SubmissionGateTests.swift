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

    func testSubmissionGateRefusesToReplaceTheRunningSubmission() {
        // The submission gate refuses a second task while the first is active.
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

    func testAnUndoWhoseRemoteOutcomeIsUnknownIsNotOfferedAgainAndIsNotDescribedAsStillInPlace() {
        let unknown: [String: Any] = ["status": "failed", "code": "undo_outcome_unknown"]
        XCTAssertFalse(UndoConfirmation.isRetryable(unknown))
        XCTAssertFalse(UndoConfirmation.failureMessage(unknown).contains("may still be in place"))
        XCTAssertTrue(UndoConfirmation.failureMessage(unknown).contains("will not send it again"))
        XCTAssertFalse(UndoConfirmation.isRetryable(["status": "refused", "code": "undo_outcome_unknown"]))
    }

    func testAnUndoThatProvablyChangedNothingOrGotNoAnswerKeepsItsHandle() {
        let failed: [String: Any] = ["status": "failed", "code": "undo_failed"]
        XCTAssertTrue(UndoConfirmation.isRetryable(failed))
        XCTAssertTrue(UndoConfirmation.isRetryable(nil))
        XCTAssertTrue(UndoConfirmation.failureMessage(failed).contains("may still be in place"))
        XCTAssertTrue(UndoConfirmation.failureMessage(nil).contains("may still be in place"))
        XCTAssertFalse(UndoConfirmation.isRetryable(["status": "refused", "code": "already_undone"]))
    }
}
