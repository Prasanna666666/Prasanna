import Foundation

/// The Core calls one asked question needs. `CoreClient` is the real one; the tests use a scripted one.
public protocol QuestionClient: AnyObject {
    func ask(question: String, scope: [String]) throws -> String
    func state(_ taskID: String) throws -> String
    func cancel(_ taskID: String) throws
    func answer(_ taskID: String) throws -> [String: Any]
}

extension CoreClient: QuestionClient {}

/// The owner's Stop for the question that is running. It may be pressed before the Core has returned the task ID (it is then applied to that task
/// as soon as the ID arrives), while the task runs, or after it ended (then it does nothing). A new question clears it, so a Stop can never cancel an
/// earlier turn. Used from the main actor only (the app model and `QuestionRunner`).
public final class StopSignal {
    private var cancellation = SubmissionCancellation()
    public init() {}

    public var taskID: String? { cancellation.taskID }
    public func begin() { cancellation.begin() }
    public func end() { cancellation.end() }
    /// True when Stop was pressed before the ID was known.
    public func bind(_ id: String) -> Bool { cancellation.bind(id) }
    /// Records the Stop and returns the task to cancel now, if its ID is known.
    public func request() -> String? { cancellation.request() }
}

/// How a question ended, as the app shows it. `answered` only for a completed task (with or without limitations); a cancelled, expired or failed
/// task ends with its own phase and its answer is never fetched, so Stop shows Cancelled and running out of time shows Expired, never Failed.
public enum QuestionOutcome {
    case answered(TaskPhase, [String: Any])
    case ended(TaskPhase)
}

@MainActor
public enum QuestionRunner {
    /// Ask one question and follow it to its end. `onID` is called once the Core has returned the task ID, `onState` with every Core state seen,
    /// `onStopFailed` if a Stop could not be delivered (the task then simply runs on and ends as the Core says).
    public static func run(
        client: QuestionClient, question: String, scope: [String], stop: StopSignal, pollNanoseconds: UInt64 = 300_000_000,
        onID: (String) -> Void = { _ in }, onState: (String) -> Void = { _ in }, onStopFailed: () -> Void = {}
    ) async throws -> QuestionOutcome {
        stop.begin()
        defer { stop.end() }
        let id = try await Task.detached { try client.ask(question: question, scope: scope) }.value
        let stopNow = stop.bind(id)
        onID(id)
        if stopNow {
            do { try await Task.detached { try client.cancel(id) }.value } catch { onStopFailed() }
        }
        var phase = TaskPhase.unknown
        while true {
            let state = try await Task.detached { try client.state(id) }.value
            onState(state)
            phase = TaskPhase.from(coreState: state)
            if phase.isTerminal || phase == .unknown { break }
            try await Task.sleep(nanoseconds: pollNanoseconds)
        }
        guard phase == .completed || phase == .completedWithLimitations else { return .ended(phase) }
        let raw = try await Task.detached { try client.answer(id) }.value
        return .answered(phase, raw)
    }

    /// The owner pressed Stop: cancel the running task now if its ID is known, or have `run` cancel it the moment the ID arrives. Returns whether a
    /// cancel request was sent now; throws if it could not be delivered.
    @discardableResult
    public static func stop(client: QuestionClient, signal: StopSignal) async throws -> Bool {
        guard let id = signal.request() else { return false }
        try await Task.detached { try client.cancel(id) }.value
        return true
    }
}
