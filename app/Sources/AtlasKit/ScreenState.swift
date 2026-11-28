import Foundation

/// Why a surface cannot show its content. Each reason has plain words; none is a raw code.
public enum UnavailableReason: Equatable {
    case coreStarting, coreUnreachable, notAvailableYet, unknownState

    public var message: String {
        switch self {
        case .coreStarting: return "Atlas is starting. This will be ready in a moment."
        case .coreUnreachable: return "Atlas is not running or cannot be reached. Open Atlas and try again."
        case .notAvailableYet: return "This is not available yet."
        case .unknownState: return "Atlas cannot show this right now. Update the app if this keeps happening."
        }
    }
}

/// The states every data surface must account for (UI/UX specification section 11), so no screen can fall through to a blank panel.
public enum LoadState<Value> {
    case idle
    case loading
    case loaded(Value)
    case empty
    case partial(Value, note: String)
    case unavailable(UnavailableReason)
    case denied(String)
    case failed(String)

    /// What to say when there is no content; nil when there is content to show.
    public var notice: String? {
        switch self {
        case .idle, .loaded, .partial: return nil
        case .loading: return "Loading."
        case .empty: return "Nothing here yet."
        case .unavailable(let reason): return reason.message
        case .denied(let text), .failed(let text): return text
        }
    }

    public var isIdle: Bool {
        if case .idle = self { return true }
        return false
    }

    public var hasContent: Bool {
        switch self {
        case .loaded, .partial: return true
        default: return false
        }
    }
}

/// The app's own launch state, shown before any screen (first launch, returning launch, Core starting, Core unavailable).
public enum LaunchState: Equatable {
    case startingCore, needsOwnerSignIn, identityUnavailable(String), coreUnavailable(String), ready

    public var message: String? {
        switch self {
        case .startingCore: return UnavailableReason.coreStarting.message
        case .needsOwnerSignIn: return "This Mac needs you to sign in before Atlas can start."
        case .identityUnavailable(let text), .coreUnavailable(let text): return text
        case .ready: return nil
        }
    }

    /// The owner's identity could not be created or read in the Keychain. Nothing can be asked or changed without it, so this blocks the app with a next step instead of showing a composer that cannot work.
    public static let identityFailureMessage = "Atlas could not open this Mac's secure storage (Keychain), so it cannot start. Unlock your Mac or sign in again, then reopen Atlas. If it keeps happening, restart your Mac."

    /// Resolves the owner's identity from a provider. A failure is kept as a launch state, never discarded.
    public static func resolveIdentity<Identity>(_ provider: () throws -> Identity) -> (identity: Identity?, state: LaunchState?) {
        do { return (try provider(), nil) } catch { return (nil, .identityUnavailable(identityFailureMessage)) }
    }

    /// Maps the launcher's failure text to a launch state.
    public static func from(launchError text: String) -> LaunchState {
        text.contains("needs owner sign-in") ? .needsOwnerSignIn : .coreUnavailable(UnavailableReason.coreUnreachable.message)
    }
}

/// The conversation surface's states.
public enum ConversationState: Equatable {
    case empty, composing, submitted, running(TaskPhase), finished(TaskPhase), failed(String)

    public static func from(phase: TaskPhase?, composing: Bool, failure: String?) -> ConversationState {
        if let failure { return .failed(failure) }
        guard let phase else { return composing ? .composing : .empty }
        return phase.isTerminal ? .finished(phase) : (phase == .received ? .submitted : .running(phase))
    }
}

/// Evidence for one citation: what the inspector can honestly say.
public enum EvidenceState: Equatable {
    case available(String), missing, stale, sourceDenied, unsupportedLocator

    public var message: String? {
        switch self {
        case .available: return nil
        case .missing: return "The passage could not be found. The source may have changed or been removed."
        case .stale: return "This source has changed since Atlas read it, so the passage may no longer match."
        case .sourceDenied: return "Atlas is no longer allowed to open this source."
        case .unsupportedLocator: return "Atlas cannot point to the exact place in this source."
        }
    }

    /// Maps the Core's answer to a passage request.
    public static func from(coreCode code: String?, text: String?) -> EvidenceState {
        switch code {
        case nil: return text.map { EvidenceState.available($0) } ?? .missing
        case "source_denied": return .sourceDenied
        case "conflict": return .stale
        case "not_found": return .missing
        default: return .unsupportedLocator
        }
    }
}
