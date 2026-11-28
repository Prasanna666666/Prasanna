import Foundation

/// Connections (UI/UX specification: connected services are shown with what they can do, what asks you first, and how to disconnect). Every integration is described by the Core's catalogue, so a new one
/// appears here with no change to the app; the words below turn the Core's codes into plain language.
public struct ConnectorView: Equatable, Identifiable {
    public enum State: Equatable { case notConnected, connected, needsAttention(String) }

    public struct Change: Equatable { public let title: String; public let approvalNote: String; public let asksFirst: Bool }

    public let id: String
    public let title: String
    public let summary: String
    public let state: State
    public let reads: String
    public let changes: [Change]
    public let offline: String
    public let retention: String
    public let failure: String

    public var stateLine: String {
        switch state {
        case .notConnected: return "Not connected"
        case .connected: return "Connected"
        case .needsAttention(let why): return "Needs attention. " + why
        }
    }

    public var isConnected: Bool {
        if case .notConnected = state { return false }
        return true
    }
}

public enum ConnectionsOutcome {
    static func scopeWords(_ scope: String) -> String { scope.replacingOccurrences(of: "_", with: " ") }

    public static func problem(_ code: String?) -> String {
        switch code {
        case "unauthorised": return "The service did not accept the access token."
        case "unreachable": return "The service did not answer."
        case "unverified": return "Atlas is checking this service."
        default: return "Atlas could not reach this service."
        }
    }

    public static func from(_ response: [String: Any]) -> LoadState<[ConnectorView]> {
        guard let rows = response["connectors"] as? [[String: Any]] else { return .unavailable(.unknownState) }
        let views = rows.compactMap { view(from: $0) }
        return views.isEmpty ? .empty : .loaded(views)
    }

    public static func view(from row: [String: Any]) -> ConnectorView? {
        guard let id = row["id"] as? String, let title = row["title"] as? String, let summary = row["summary"] as? String, let state = row["state"] as? String else { return nil }
        let parsed: ConnectorView.State
        switch state {
        case "connected": parsed = .connected
        case "needs_attention": parsed = .needsAttention(problem(row["problem"] as? String))
        default: parsed = .notConnected
        }
        let reads = (row["read_scopes"] as? [String] ?? []).map(scopeWords).joined(separator: ", ")
        let changes = (row["writes"] as? [[String: Any]] ?? []).compactMap { write -> ConnectorView.Change? in
            guard let name = write["title"] as? String, let approval = write["approval"] as? String else { return nil }
            let asks = approval == "always"
            return ConnectorView.Change(title: name, approvalNote: asks ? "Atlas asks you first, every time." : "Atlas does this without asking, and you can undo it.", asksFirst: asks)
        }
        return ConnectorView(
            id: id, title: title, summary: summary, state: parsed,
            reads: reads.isEmpty ? "Nothing" : reads.prefix(1).uppercased() + reads.dropFirst(),
            changes: changes, offline: row["offline"] as? String ?? "", retention: row["retention"] as? String ?? "", failure: row["failure"] as? String ?? ""
        )
    }
}

/// What the owner types to connect: where the service is and the access token. Validation says what is wrong in plain words; the token is only ever sent to the Core.
public struct ConnectDraft: Equatable {
    public var address = ""
    public var token = ""

    public init() {}

    public func problem() -> String? {
        let trimmed = address.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http", url.host != nil else {
            return "Enter the address of the service. It starts with https."
        }
        if scheme == "http", !ConnectDraft.isHomeNetwork(url.host ?? "") { return "Use an https address for a service on the Internet. A plain http address is only for your own home network." }
        if token.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "Enter the access token the service gave you." }
        return nil
    }

    /// Loopback, private ranges, the shared VPN range and `.local` and VPN names: where plain http is allowed (the Core enforces the same rule).
    static func isHomeNetwork(_ host: String) -> Bool {
        if host == "localhost" || host.hasSuffix(".local") || host.hasSuffix(".ts.net") { return true }  // .ts.net: a VPN's own names, which resolve inside the encrypted private network
        let parts = host.split(separator: ".").compactMap { Int($0) }
        guard parts.count == 4 else { return false }
        return parts[0] == 127 || parts[0] == 10 || (parts[0] == 192 && parts[1] == 168) || (parts[0] == 172 && (16...31).contains(parts[1])) || (parts[0] == 169 && parts[1] == 254) || (parts[0] == 100 && (64...127).contains(parts[1]))
    }

    public var fields: [String: String] { ["address": address.trimmingCharacters(in: .whitespacesAndNewlines), "token": token.trimmingCharacters(in: .whitespacesAndNewlines)] }
}
