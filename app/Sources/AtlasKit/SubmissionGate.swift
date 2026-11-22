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
