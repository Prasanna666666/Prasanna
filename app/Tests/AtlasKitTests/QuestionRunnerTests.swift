import XCTest
@testable import AtlasKit

/// UC-009 at the app-model level: the question flow the app model runs (QuestionRunner) against a scripted Core, for every Stop timing. Stop shows
/// Cancelled whether it is pressed before the task ID returns, while the task runs, or after it completed; Cancelled and Expired are never shown
/// as Failed, and a cancelled or expired task's answer is never fetched.
@MainActor
final class QuestionRunnerTests: XCTestCase {
    /// A scripted Core: `states` is what successive state polls return; once `cancel` is called every later poll returns "cancelled".
    final class ScriptedCore: QuestionClient {
        var states: [String]
        var cancelled: [String] = []
        var answers = 0
        var onAsk: () -> Void = {}
        var onState: (Int) -> Void = { _ in }
        private var polls = 0
        init(states: [String]) { self.states = states }

        func ask(question: String, scope: [String]) throws -> String { onAsk(); return "task-1" }
        func state(_ taskID: String) throws -> String {
            polls += 1
            onState(polls)
            if !cancelled.isEmpty { return "cancelled" }
            return states.isEmpty ? "completed" : states.removeFirst()
        }
        func cancel(_ taskID: String) throws { cancelled.append(taskID) }
        func answer(_ taskID: String) throws -> [String: Any] { answers += 1; return ["text": "done", "citations": []] }
    }

    private func phase(_ outcome: QuestionOutcome) -> TaskPhase {
        switch outcome {
        case .answered(let phase, _): return phase
        case .ended(let phase): return phase
        }
    }

    func testStopPressedBeforeTheTaskIDReturnsCancelsThatTaskAndShowsCancelled() async throws {
        let core = ScriptedCore(states: ["queued", "running", "running"])
        let stop = StopSignal()
        core.onAsk = { XCTAssertNil(stop.request()) }  // the owner presses Stop while the Core has not answered with an ID yet
        let outcome = try await QuestionRunner.run(client: core, question: "q", scope: ["documents"], stop: stop, pollNanoseconds: 1_000)
        XCTAssertEqual(core.cancelled, ["task-1"])
        XCTAssertEqual(phase(outcome), .cancelled)
        XCTAssertEqual(core.answers, 0)  // never fetched, so never turned into Failed
    }

    func testStopPressedWhileTheTaskRunsShowsCancelledNotFailed() async throws {
        let core = ScriptedCore(states: ["queued"] + Array(repeating: "running", count: 400))  // still running whenever the Stop lands
        let stop = StopSignal()
        final class Sent { var value = false }
        let sent = Sent()
        core.onState = { poll in
            if poll == 2 { Task { @MainActor in sent.value = (try? await QuestionRunner.stop(client: core, signal: stop)) ?? false } }
        }
        let outcome = try await QuestionRunner.run(client: core, question: "q", scope: ["documents"], stop: stop, pollNanoseconds: 2_000_000)
        XCTAssertTrue(sent.value)
        XCTAssertEqual(phase(outcome), .cancelled)
        XCTAssertNotEqual(phase(outcome), .failed)
        XCTAssertEqual(core.answers, 0)
    }

    func testStopPressedAfterTheTaskCompletedChangesNothing() async throws {
        let core = ScriptedCore(states: ["running", "completed"])
        let stop = StopSignal()
        let outcome = try await QuestionRunner.run(client: core, question: "q", scope: ["documents"], stop: stop, pollNanoseconds: 1_000)
        let sent = try await QuestionRunner.stop(client: core, signal: stop)
        XCTAssertFalse(sent)
        XCTAssertTrue(core.cancelled.isEmpty)
        XCTAssertEqual(phase(outcome), .completed)
        XCTAssertEqual(core.answers, 1)
    }

    func testAnExpiredTaskShowsExpiredNeverFailedAndItsAnswerIsNotFetched() async throws {
        let core = ScriptedCore(states: ["running", "expired"])
        let outcome = try await QuestionRunner.run(client: core, question: "q", scope: ["documents"], stop: StopSignal(), pollNanoseconds: 1_000)
        XCTAssertEqual(phase(outcome), .expired)
        XCTAssertEqual(core.answers, 0)
    }

    func testANewQuestionNeverCarriesThePreviousStop() async throws {
        let stop = StopSignal()
        let first = ScriptedCore(states: ["completed"])
        _ = try await QuestionRunner.run(client: first, question: "q1", scope: ["documents"], stop: stop, pollNanoseconds: 1_000)
        XCTAssertNil(stop.request())  // a Stop after the first ended is not remembered for the next question
        let second = ScriptedCore(states: ["running", "completed"])
        let outcome = try await QuestionRunner.run(client: second, question: "q2", scope: ["documents"], stop: stop, pollNanoseconds: 1_000)
        XCTAssertTrue(second.cancelled.isEmpty)
        XCTAssertEqual(phase(outcome), .completed)
    }
}
