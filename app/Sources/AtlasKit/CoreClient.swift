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

    public func consent() throws -> [String: Any] { try object(call("GET", "/v1/consent")) }
    public func enable(_ sources: [String]) throws -> [String: Any] { try object(call("POST", "/v1/consent", ["sources": sources])) }
    public func withdraw(grantID: String) throws -> [String: Any] { try object(call("DELETE", "/v1/consent/\(grantID)")) }
    public func indexStatus() throws -> [String: Any] { try object(call("GET", "/v1/index/status")) }
}
