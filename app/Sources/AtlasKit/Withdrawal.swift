import Foundation

/// What the screen does when the owner withdraws access to a source (MAC-20): every result shown from that source is taken off, every answer
/// that cites it is replaced by a plain notice, and a search or answer that comes back after the change is discarded instead of shown.
public enum Withdrawal {
    public static let removedNotice = "Removed: you turned off a source this answer used."

    /// The Library after `withdrawn` source types lost access: their results are gone; a page left with nothing says so.
    public static func library(_ state: LoadState<LibraryPage>, withdrawn: Set<String>) -> LoadState<LibraryPage> {
        guard !withdrawn.isEmpty else { return state }
        switch state {
        case .loaded(let page):
            let kept = LibraryPage(results: page.results.filter { !withdrawn.contains($0.sourceType) }, coverageLine: page.coverageLine)
            return kept.results.isEmpty ? .empty : .loaded(kept)
        case .partial(let page, let note):
            let kept = LibraryPage(results: page.results.filter { !withdrawn.contains($0.sourceType) }, coverageLine: page.coverageLine)
            return kept.results.isEmpty ? .empty : .partial(kept, note: note)
        default:
            return state
        }
    }

    /// Whether an answer must be taken off the screen because it cites a source that is no longer allowed.
    public static func hides(_ answer: AnswerView, withdrawn: Set<String>) -> Bool { !answer.sourceTypes.isDisjoint(with: withdrawn) }
}

/// Stale continuations: work started before access changed is not shown when it comes back. Take a token before the request; after it, show the
/// result only if the token is still current. A withdrawal advances the generation.
public final class ResultGeneration {
    private var value = 0
    public init() {}
    public func token() -> Int { value }
    public func advance() { value += 1 }
    public func isCurrent(_ token: Int) -> Bool { token == value }
}
