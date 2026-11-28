import Foundation

/// What the owner sees when an action needs approval (UI/UX specification 4.8; PRD 4.4). It shows the exact action and payload in plain words. A material change to the payload invalidates the
/// approval, nothing is approved without a deliberate tap, and an action Atlas cannot describe is never presented for approval.
public struct ApprovalRow: Equatable { public let label: String; public let value: String }

public enum ApprovalState: Equatable {
    case pending, invalidated, approved, declined, expired, completed, failed(String)
}

public struct ApprovalSummary: Equatable {
    public let approvalID: String
    public let action: String
    public let title: String
    public let rows: [ApprovalRow]
    public let consequence: String
    public let category: Int
    /// A stable text of the exact payload, used only to detect that it changed.
    let fingerprint: String
}

public enum ApprovalDescriber {
    private static let titles: [String: String] = [
        "calendar.send_invitation": "Send a calendar invitation",
        "notes.erase": "Permanently erase a note",
        "calendar.erase": "Permanently erase a calendar event",
        "contacts.erase": "Permanently erase a contact",
    ]

    private static let consequences: [Int: String] = [
        1: "This sends information outside your Mac.",
        2: "This spends money.",
        3: "This cannot be undone.",
        4: "This changes physical access or a safety system.",
    ]

    static func humanise(_ key: String) -> String {
        let spaced = key.replacingOccurrences(of: "_", with: " ")
        return spaced.prefix(1).uppercased() + spaced.dropFirst()
    }

    static func render(_ value: Any) -> String {
        if let text = value as? String { return text }
        if let flag = value as? Bool { return flag ? "Yes" : "No" }
        if let number = value as? NSNumber { return number.stringValue }
        if JSONSerialization.isValidJSONObject(value), let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]), let text = String(data: data, encoding: .utf8) { return text }
        return "\(value)"
    }

    /// Nil when the action or category is not one Atlas can describe in plain words: such an action is never shown for approval.
    public static func describe(approvalID: String, action: String, payload: [String: Any], category: Int) -> ApprovalSummary? {
        guard let title = titles[action], let consequence = consequences[category] else { return nil }
        let rows = payload.keys.sorted().map { ApprovalRow(label: humanise($0), value: render(payload[$0] as Any)) }
        let fingerprint = rows.map { "\($0.label)=\($0.value)" }.joined(separator: "\n")
        return ApprovalSummary(approvalID: approvalID, action: action, title: title, rows: rows, consequence: consequence, category: category, fingerprint: fingerprint)
    }
}

public struct ApprovalFlow: Equatable {
    public private(set) var summary: ApprovalSummary
    public private(set) var state: ApprovalState = .pending
    public let expiresAt: Date

    public init(summary: ApprovalSummary, expiresAt: Date) { self.summary = summary; self.expiresAt = expiresAt }

    /// The owner can approve only while the approval is pending and has not run out.
    public func canApprove(now: Date) -> Bool { state == .pending && now < expiresAt }

    public mutating func expireIfDue(now: Date) { if state == .pending && now >= expiresAt { state = .expired } }

    /// If the payload shown is no longer the exact payload, the approval is invalid and a new one must be asked for.
    public mutating func payloadChanged(to payload: [String: Any]) {
        guard state == .pending || state == .approved else { return }
        if let updated = ApprovalDescriber.describe(approvalID: summary.approvalID, action: summary.action, payload: payload, category: summary.category), updated.fingerprint != summary.fingerprint {
            state = .invalidated
        }
    }

    public mutating func approved(now: Date) -> Bool {
        guard canApprove(now: now) else { return false }
        state = .approved
        return true
    }

    public mutating func declined() { if state == .pending { state = .declined } }
    public mutating func finished(success: Bool, message: String) { if state == .approved { state = success ? .completed : .failed(message) } }
}
