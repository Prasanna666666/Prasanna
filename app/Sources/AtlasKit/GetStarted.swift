import Foundation

/// The first-run choice, as data. Nothing is enabled until the owner deliberately switches it on: the default is everything off, and continuing with nothing enabled is a valid choice
/// (default-deny: no grant exists until the owner creates it).
public struct GetStartedChoice: Equatable {
    public var documents = false
    public var mail = false
    public init(documents: Bool = false, mail: Bool = false) { self.documents = documents; self.mail = mail }

    /// The source types the owner chose, in a fixed order.
    public var sources: [String] { (documents ? ["documents"] : []) + (mail ? ["mail"] : []) }
    /// Continuing is always possible, including with nothing selected.
    public var canContinue: Bool { true }
}

public enum GetStartedFlow {
    /// What to ask the Core to enable: nil when nothing was chosen (no request is made, so no grant can come into being).
    public static func request(for choice: GetStartedChoice) -> [String]? { choice.sources.isEmpty ? nil : choice.sources }

    /// Get Started is shown until the owner has completed it once (even with nothing enabled) or already has an active grant.
    public static func needsGetStarted(completedOnce: Bool, activeGrants: Int) -> Bool { !completedOnce && activeGrants == 0 }
}
