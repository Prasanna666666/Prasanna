import CryptoKit
import Foundation

/// The signed message of the Core API (core/docs/CONTRACT_1_1.md, "Signing"): LF-joined fields, no trailing newline.
/// 1.0: METHOD, target, timestamp, nonce, sha256hex(body). 1.1: the literal "1.1" first. `/v1/version` is always signed as 1.0.
public enum Signing {
    public static func message(version: String, method: String, target: String, timestamp: String, nonce: String, body: Data) -> Data {
        let digest = SHA256.hash(data: body).map { String(format: "%02x", $0) }.joined()
        var fields = [method.uppercased(), target, timestamp, nonce, digest]
        if version != "1.0" { fields.insert(version, at: 0) }
        precondition(!fields.contains { $0.contains("\n") || $0.contains("\r") }, "a signed field may not contain CR or LF")
        return Data(fields.joined(separator: "\n").utf8)
    }

    /// The headers a request carries. `version` "1.1" also sends the version header (it is part of the signed message).
    public static func headers(signer: Curve25519.Signing.PrivateKey, clientID: String, version: String, method: String, target: String, body: Data, now: Date = Date()) throws -> [String: String] {
        let timestamp = String(Int(now.timeIntervalSince1970))
        var bytes = [UInt8](repeating: 0, count: 12)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw AtlasError.local("no random nonce") }
        let nonce = bytes.map { String(format: "%02x", $0) }.joined()
        let signature = try signer.signature(for: message(version: version, method: method, target: target, timestamp: timestamp, nonce: nonce, body: body))
        var out = ["x-atlas-client": clientID, "x-atlas-timestamp": timestamp, "x-atlas-nonce": nonce, "x-atlas-signature": signature.base64EncodedString()]
        if version != "1.0" { out["x-atlas-api-version"] = version }
        return out
    }
}
