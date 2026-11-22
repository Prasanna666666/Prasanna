import CryptoKit
import XCTest
@testable import AtlasKit

/// Known-answer vectors from core/docs/CONTRACT_1_1.md (inputs: method post, target /v1/tasks?after=0, timestamp 1700000000, nonce abcdefgh12345678, body {"a":1}).
final class SigningTests: XCTestCase {
    let body = Data(#"{"a":1}"#.utf8)
    func hex(_ d: Data) -> String { d.map { String(format: "%02x", $0) }.joined() }

    func testVersion10MessageMatchesTheSpecificationVector() {
        let m = Signing.message(version: "1.0", method: "post", target: "/v1/tasks?after=0", timestamp: "1700000000", nonce: "abcdefgh12345678", body: body)
        XCTAssertEqual(hex(m), "504f53540a2f76312f7461736b733f61667465723d300a313730303030303030300a616263646566676831323334353637380a30313561626437663563633537613264643934623735393066303461643830383432373339303565653333656335636562656165363232373661393766383632")
    }

    func testVersion11MessageMatchesTheSpecificationVector() {
        let m = Signing.message(version: "1.1", method: "post", target: "/v1/tasks?after=0", timestamp: "1700000000", nonce: "abcdefgh12345678", body: body)
        XCTAssertEqual(hex(m), "312e310a504f53540a2f76312f7461736b733f61667465723d300a313730303030303030300a616263646566676831323334353637380a30313561626437663563633537613264643934623735393066303461643830383432373339303565653333656335636562656165363232373661393766383632")
    }

    func testTheSignatureVerifiesUnderThePublicKeyAndTheHeaderIsSentOnlyFor11() throws {
        let key = Curve25519.Signing.PrivateKey()
        let h = try Signing.headers(key: key, clientID: "owner-mac-0001", version: "1.1", method: "GET", target: "/v1/consent", body: Data())
        let signature = Data(base64Encoded: h["x-atlas-signature"]!)!
        let message = Signing.message(version: "1.1", method: "GET", target: "/v1/consent", timestamp: h["x-atlas-timestamp"]!, nonce: h["x-atlas-nonce"]!, body: Data())
        XCTAssertTrue(key.publicKey.isValidSignature(signature, for: message))
        XCTAssertEqual(h["x-atlas-api-version"], "1.1")
        XCTAssertNil(try Signing.headers(key: key, clientID: "c", version: "1.0", method: "GET", target: "/v1/version", body: Data())["x-atlas-api-version"])
    }

    func testTheCatalogueLoadsAndAnswerViewsUsePlainWords() {
        let view = AnswerView(["answer": "A", "verification": ["status": "verified"], "limitations": ["language_unmeasured"], "not_searched": [], "citations": [],
                               "model": ["model_id": "primary-1", "role": "primary", "runtime": "mlx"], "coverage": ["state": "complete", "searched": 3, "total": 3, "pending": [], "failed": []]])
        XCTAssertTrue(view.modelLine.contains("primary-1") && view.modelLine.contains("Nothing left your computer"))
        XCTAssertEqual(view.notices, [Catalogue.shared.limitations["language_unmeasured"]!])
        XCTAssertTrue(view.coverageLine!.contains("Searched 3 of 3"))
    }
}
