import CryptoKit
import Foundation

/// The conversation path over the signed contract: ask, poll, cancel, answer, passage, consent. Mirrors core/client/atlas_client.py (the verified reference).
public final class CoreClient {
    public let transport: UnixHTTP
    private let signer: Curve25519.Signing.PrivateKey
    private let clientID: String
    private let version = "1.1"

    public init(socketPath: String, signer: Curve25519.Signing.PrivateKey, clientID: String) {
        transport = UnixHTTP(path: socketPath); self.signer = signer; self.clientID = clientID
    }

    private func call(_ method: String, _ target: String, _ body: [String: Any]? = nil, signed: Bool = true) throws -> Any {
        let data = try body.map { try JSONSerialization.data(withJSONObject: $0) } ?? Data()
        let headers = signed ? try Signing.headers(signer: signer, clientID: clientID, version: version, method: method, target: target, body: data) : ["x-atlas-api-version": version]
        let response = try transport.send(method: method, target: target, headers: headers.merging(["content-type": "application/json"]) { $1 }, body: data)
        guard response.headers["x-atlas-api-version"] == version else { throw AtlasError.core(code: "unsupported_version") }  // a 1.1 client rejects a missing or different echo
        let value = (try? JSONSerialization.jsonObject(with: response.body)) ?? [:]
        if response.status >= 400 {
            let code = (value as? [String: Any])?["code"] as? String ?? "internal_error"
            throw AtlasError.core(code: Catalogue.shared.errors[code] != nil ? code : "internal_error")
        }
        return value
    }

    private func object(_ value: Any) throws -> [String: Any] {
        guard let dictionary = value as? [String: Any] else { throw AtlasError.core(code: "internal_error") }
        return dictionary
    }

    public func ask(question: String, scope: [String]) throws -> String {
        let record = try object(call("POST", "/v1/tasks", ["objective": question, "source_scope": scope, "budget": ["max_seconds": 120, "max_retries": 1], "idempotency_key": UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()]))
        return record["task_id"] as? String ?? ""
    }

    public func state(_ taskID: String) throws -> String { try object(call("GET", "/v1/tasks/\(taskID)"))["state"] as? String ?? "failed" }
    public func cancel(_ taskID: String) throws { _ = try call("POST", "/v1/tasks/\(taskID)/cancel") }
    public func answer(_ taskID: String) throws -> [String: Any] { try object(call("GET", "/v1/tasks/\(taskID)/answer")) }
    public func passage(_ taskID: String, index: Int) throws -> String { try object(call("GET", "/v1/tasks/\(taskID)/citations/\(index)"))["text"] as? String ?? "" }
    public func compute(kind: String, args: [String]) throws -> [String: Any] { try object(call("POST", "/v1/compute", ["kind": kind, "args": args])) }
    /// First run: enrol this client's public key as the OWNER client. Unsigned and accepted once, over the owner-only socket, while no owner client exists; afterwards the Core refuses it.
    /// `bootstrapCode` is the single-use first-run code the process that STARTED the Core handed to this app over a private channel; without it a Core started normally refuses.
    public func enrolSelf(bootstrapCode: String?) throws {
        var body: [String: Any] = ["client_id": clientID, "public_key": signer.publicKey.rawRepresentation.base64EncodedString(), "role": "owner"]
        if let bootstrapCode { body["bootstrap_code"] = bootstrapCode }
        _ = try call("POST", "/v1/enrol", body, signed: false)
    }

    public func mode() throws -> String { try object(call("GET", "/v1/mode"))["mode"] as? String ?? "default" }
    public func setMode(_ mode: String) throws -> String { try object(call("POST", "/v1/mode", ["mode": mode]))["mode"] as? String ?? "default" }
    public func consent() throws -> [String: Any] { try object(call("GET", "/v1/consent")) }
    public func enable(_ sources: [String]) throws -> [String: Any] { try object(call("POST", "/v1/consent", ["sources": sources])) }
    public func withdraw(grantID: String) throws -> [String: Any] { try object(call("DELETE", "/v1/consent/\(grantID)")) }
    public func indexStatus() throws -> [String: Any] { try object(call("GET", "/v1/index/status")) }

    /// Propose one typed action as the owner. The answer is done, needs_approval (with the exact payload and an approval id), refused or failed.
    public func act(_ action: String, payload: [String: Any], approvalID: String? = nil) throws -> [String: Any] {
        var body: [String: Any] = ["action": action, "payload": payload, "idempotency_key": UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()]
        if let approvalID { body["approval_id"] = approvalID }
        return try object(call("POST", "/v1/actions", body))
    }

    public func approve(approvalID: String) throws -> Bool { (try object(call("POST", "/v1/actions/approve", ["approval_id": approvalID])))["granted"] as? Bool ?? false }
    public func undo(actionID: String) throws -> [String: Any] { try object(call("POST", "/v1/actions/undo", ["action_id": actionID])) }

    /// Library search over the enabled sources: results plus how much of each source has been read.
    public func librarySearch(_ query: String, scope: [String]) throws -> [String: Any] { try object(call("POST", "/v1/library/search", ["query": query, "scope": scope])) }

    /// Paired devices (owner only), a pairing offer for a new device, and revocation.
    public func devices() throws -> [[String: Any]] { (try object(call("GET", "/v1/devices")))["devices"] as? [[String: Any]] ?? [] }
    public func openPairingOffer() throws -> [String: Any] { try object(call("POST", "/v1/devices/offer", [:])) }
    public func revokeDevice(_ deviceID: String) throws -> Bool { (try object(call("POST", "/v1/devices/revoke", ["device_id": deviceID])))["revoked"] as? Bool ?? false }
}
