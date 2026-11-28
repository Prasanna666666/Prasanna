import Foundation

/// One question at a time. The gate lives in the model, not only on the button: pressing Enter in the text field while a question is running must not start a second task.
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

    static let notConfirmed = "Atlas could not confirm the undo. The original change may still be in place."
    static let outcomeUnknown =
        "Atlas sent the undo, but the service did not confirm it. To avoid applying it twice, Atlas will not send it again: check the service to see whether the change was undone."

    /// What the owner is told when the undo was not confirmed. A remote compensation with an unknown outcome (`undo_outcome_unknown`) may have
    /// been applied, so it is never described as the change still being in place.
    public static func failureMessage(_ response: [String: Any]?) -> String {
        response?["code"] as? String == "undo_outcome_unknown" ? outcomeUnknown : notConfirmed
    }

    /// Whether pressing Undo again can help. The Core refuses a second compensation whose outcome is unknown, and an action that was already
    /// undone, is not reversible or is not known; only a failure that provably changed nothing (or a request that never got an answer) keeps
    /// the Undo handle.
    public static func isRetryable(_ response: [String: Any]?) -> Bool {
        guard let response else { return true }  // the request itself failed: the Core may not have seen it
        let terminal: Set<String> = ["undo_outcome_unknown", "already_undone", "not_reversible", "unknown_action_id"]
        return !terminal.contains(response["code"] as? String ?? "")
    }
}
