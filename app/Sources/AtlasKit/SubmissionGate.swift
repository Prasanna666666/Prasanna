import Foundation

/// One question at a time. The gate lives in the model, not only on the button: pressing Enter in the text field while a question is running must not start a second task (which would
/// overwrite the task id, so Cancel would stop only the newer one and the first would run on).
public struct SubmissionGate {
    public private(set) var busy = false
    public init() {}

    /// True if this submission may start (and the gate is now held); false if one is already running.
    public mutating func begin() -> Bool {
        if busy { return false }
        busy = true
        return true
    }

    public mutating func end() { busy = false }
}

/// Tracks the ID of the current submission and a Stop request made before Core returns that ID.
/// A new submission clears the previous ID so Stop can never cancel a prior turn.
public struct SubmissionCancellation {
    public private(set) var taskID: String?
    public private(set) var requested = false
    public init() {}

    public mutating func begin() {
        taskID = nil
        requested = false
    }

    /// Returns true when a Stop request arrived before the task ID was known.
    public mutating func bind(_ id: String) -> Bool {
        taskID = id
        return requested
    }

    /// Records Stop intent and returns the current task ID, if Core has supplied it.
    public mutating func request() -> String? {
        requested = true
        return taskID
    }

    public mutating func end() {
        taskID = nil
        requested = false
    }
}

/// An undo is successful only when Core explicitly confirms the terminal outcome.
public enum UndoConfirmation {
    public static func isConfirmed(_ response: [String: Any]) -> Bool {
        response["status"] as? String == "done"
    }
}
