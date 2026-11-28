import Foundation

/// Where the Mac listens for a paired phone (the optional private-network channel). Only a literal private, loopback, link-local or VPN (shared 100.64.0.0/10) IPv4 address and a port are accepted; a wildcard,
/// a name or a public address is not, so the setting can never open a port the Internet could reach. The Core applies the same rule again before it binds anything.
public enum RelayBind {
    public static func parse(_ text: String) -> String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let pieces = trimmed.split(separator: ":", omittingEmptySubsequences: false).map(String.init)
        guard pieces.count == 2, let port = Int(pieces[1]), (1024...65535).contains(port) else { return nil }
        let octets = pieces[0].split(separator: ".", omittingEmptySubsequences: false).map { Int($0) }
        guard octets.count == 4, octets.allSatisfy({ $0 != nil && (0...255).contains($0!) }) else { return nil }
        let o = octets.map { $0! }
        let isPrivate = o[0] == 127 || o[0] == 10 || (o[0] == 192 && o[1] == 168) || (o[0] == 172 && (16...31).contains(o[1])) || (o[0] == 169 && o[1] == 254) || (o[0] == 100 && (64...127).contains(o[1]))
        return isPrivate ? "\(pieces[0]):\(port)" : nil
    }

    public static let explanation = "Enter an address on your private network or VPN and a port, for example 100.64.0.5:8443. A public address is not accepted."
}
