import Foundation

/// The task lifecycle as the owner sees it (UI/UX specification 4.3): plain phases that map only from real Core states. There is no percentage and no countdown, and a state this app does not
/// know is shown as a plain "unavailable" notice, never as raw text.
public enum TaskPhase: Equatable {
    case received, checkingAccess, waiting, working, searching, preparing, checking
    case completed, completedWithLimitations, failed, cancelled, expired
    case unknown

    public static func from(coreState state: String) -> TaskPhase {
        switch state {
        case "requested": return .received
        case "policy_checked": return .checkingAccess
        case "queued": return .waiting
        case "running": return .working
        case "retrieved": return .searching
        case "drafted": return .preparing
        case "verified": return .checking
        case "completed": return .completed
        case "partially_completed": return .completedWithLimitations
        case "failed": return .failed
        case "cancelled": return .cancelled
        case "expired": return .expired
        default: return .unknown
        }
    }

    public var isTerminal: Bool {
        switch self {
        case .completed, .completedWithLimitations, .failed, .cancelled, .expired: return true
        default: return false
        }
    }

    /// Whether the Cancel control is offered: while work is going on, never after it ended.
    public var canCancel: Bool { !isTerminal && self != .unknown }

    public var label: String {
        switch self {
        case .received: return "Received"
        case .checkingAccess: return "Checking access"
        case .waiting: return "Waiting to start"
        case .working: return "Working"
        case .searching: return "Searching sources"
        case .preparing: return "Preparing an answer"
        case .checking: return "Checking the answer and citations"
        case .completed: return "Completed"
        case .completedWithLimitations: return "Completed, with limitations"
        case .failed: return "This could not be finished"
        case .cancelled: return "Cancelled"
        case .expired: return "This ran out of time"
        case .unknown: return "Atlas cannot show this state"
        }
    }

    /// Every phase carries a symbol AND a label, so status never relies on colour alone.
    public var symbol: String {
        switch self {
        case .completed: return "checkmark.circle"
        case .completedWithLimitations: return "exclamationmark.circle"
        case .failed, .expired: return "xmark.octagon"
        case .cancelled: return "stop.circle"
        case .waiting: return "hourglass"
        case .unknown: return "questionmark.circle"
        default: return "ellipsis.circle"
        }
    }
}

/// Coalesces a burst of Core states into the phases worth showing: a phase is shown only if it is different from the last one and the state moved forward, so the display never flickers back
/// and a rapid run of states shows its latest phase rather than every one.
public struct PhaseTracker {
    public private(set) var shown: TaskPhase?
    private var rank = -1
    public init() {}

    private static let order: [TaskPhase] = [.received, .checkingAccess, .waiting, .working, .searching, .preparing, .checking]

    /// Returns the phase to display after seeing `state`, or nil if the display should not change.
    public mutating func update(coreState state: String) -> TaskPhase? {
        let phase = TaskPhase.from(coreState: state)
        if phase.isTerminal || phase == .unknown { shown = phase; rank = Int.max; return phase }
        guard let index = Self.order.firstIndex(of: phase), index > rank else { return nil }
        rank = index
        shown = phase
        return phase
    }
}
