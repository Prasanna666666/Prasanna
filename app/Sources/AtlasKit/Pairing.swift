import CryptoKit
import Foundation

/// Pairing a phone with the owner's Mac (Stage 8). The Mac shows an invite; the phone pins the Core's key fingerprint from it, proves it holds the one-time code, and checks that the Core proves its own identity
/// in return, so an impostor in the middle is refused. The phone then holds its own key (in the Keychain) and is an ordinary member client, never an owner.
public struct PairingInvite: Equatable {
    public let code: String
    public let fingerprint: String
    public let address: String

    public init(code: String, fingerprint: String, address: String) { self.code = code; self.fingerprint = fingerprint; self.address = address }

    /// The invite the Mac shows: the Core's offer (a single-use code that lives five minutes and the Core's key fingerprint) plus the address the owner's phone will reach the Mac at.
    public static func make(offer: [String: Any], address: String) -> PairingInvite? {
        guard let code = offer["code"] as? String, let fingerprint = offer["core_fingerprint"] as? String else { return nil }
        let trimmed = address.trimmingCharacters(in: .whitespacesAndNewlines)
        let invite = PairingInvite(code: code, fingerprint: fingerprint, address: trimmed)
        return PairingInvite.parse(invite.text) == nil ? nil : invite  // only an invite a phone would accept is shown
    }

    /// `atlas://pair?code=…&fp=…&addr=…`: what the Mac shows (as text or a QR code) and the phone reads. Anything malformed is not an invite.
    public static func parse(_ text: String) -> PairingInvite? {
        guard let components = URLComponents(string: text.trimmingCharacters(in: .whitespacesAndNewlines)), components.scheme == "atlas", components.host == "pair" else { return nil }
        let items = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).compactMap { item in item.value.map { (item.name, $0) } })
        guard let code = items["code"], let fp = items["fp"], let addr = items["addr"] else { return nil }
        let codeOK = code.range(of: "^[A-Za-z0-9_-]{8,64}$", options: .regularExpression) != nil
        let fpOK = fp.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil
        guard codeOK, fpOK, RemoteHTTP(address: addr) != nil else { return nil }
        return PairingInvite(code: code, fingerprint: fp, address: addr)
    }

    public var text: String {
        var components = URLComponents()
        components.scheme = "atlas"
        components.host = "pair"
        components.queryItems = [URLQueryItem(name: "code", value: code), URLQueryItem(name: "fp", value: fingerprint), URLQueryItem(name: "addr", value: address)]
        return components.string ?? ""
    }
}

public struct DeviceIdentity {
    public let id: String
    public let signer: Curve25519.Signing.PrivateKey

    public init(id: String, signer: Curve25519.Signing.PrivateKey) { self.id = id; self.signer = signer }

    public static func generate() -> DeviceIdentity {
        DeviceIdentity(id: "phone-" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased().prefix(24), signer: Curve25519.Signing.PrivateKey())
    }
}

public enum PairingExchange {
    public static func nonce() -> String { UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }

    public static func request(invite: PairingInvite, label: String, identity: DeviceIdentity, nonce: String) -> [String: Any] {
        ["code": invite.code, "device_id": identity.id, "label": String(label.prefix(60)), "public_key": identity.signer.publicKey.rawRepresentation.base64EncodedString(), "nonce": nonce]
    }

    /// The device's check of the Core: the key it presented must hash to the fingerprint pinned from the invite, and must have signed THIS device's key and nonce.
    public static func verifyCore(invite: PairingInvite, identity: DeviceIdentity, nonce: String, response: [String: Any]) -> Bool {
        guard let keyText = response["core_public_key"] as? String, let proofText = response["proof"] as? String,
              let keyData = Data(base64Encoded: keyText), let proof = Data(base64Encoded: proofText),
              let coreKey = try? Curve25519.Signing.PublicKey(rawRepresentation: keyData) else { return false }
        let fingerprint = SHA256.hash(data: keyData).map { String(format: "%02x", $0) }.joined()
        guard fingerprint == invite.fingerprint else { return false }
        return coreKey.isValidSignature(proof, for: identity.signer.publicKey.rawRepresentation + Data(nonce.utf8))
    }
}

/// What the phone keeps after pairing. Stored in the Keychain on the phone; nothing else identifies it.
public struct PairedDevice: Equatable {
    public let id: String
    public let keyBytes: Data
    public let fingerprint: String
    public let address: String

    public init(id: String, keyBytes: Data, fingerprint: String, address: String) { self.id = id; self.keyBytes = keyBytes; self.fingerprint = fingerprint; self.address = address }

    public var identity: DeviceIdentity? { (try? Curve25519.Signing.PrivateKey(rawRepresentation: keyBytes)).map { DeviceIdentity(id: id, signer: $0) } }
}

public protocol DeviceVault: AnyObject {
    func load() -> PairedDevice?
    func save(_ device: PairedDevice) throws
    func erase()
}

/// For tests and previews; the phone uses the Keychain.
public final class MemoryVault: DeviceVault {
    private var device: PairedDevice?
    public init() {}
    public func load() -> PairedDevice? { device }
    public func save(_ device: PairedDevice) throws { self.device = device }
    public func erase() { device = nil }
}

public enum PairingOutcome: Equatable {
    case paired(PairedDevice)
    case failed(String)

    /// Plain words for each way pairing can fail. A wrong or expired code and an impostor are told apart, and neither stores anything.
    public static func message(forCoreCode code: String) -> String {
        switch code {
        case "forbidden", "unauthenticated": return "That code was not accepted. Ask your Mac for a new one."
        case "not_found": return "This Mac is not set up for pairing."
        default: return "Pairing did not work. Check the connection and try again."
        }
    }

    public static let impostor = "This is not the Mac that showed the code, so nothing was paired."
    public static let badInvite = "That is not an Atlas pairing code."
    public static let unreachable = "Atlas could not reach your Mac. Check the connection and try again."
}

public enum DevicePairing {
    /// Pair with the Mac named in an invite. `transportFor` makes the transport for the invite's address (the remote channel on a phone; the local socket in tests).
    public static func pair(inviteText: String, label: String, vault: DeviceVault, transportFor: (String) -> (any HTTPTransport)?) -> PairingOutcome {
        guard let invite = PairingInvite.parse(inviteText) else { return .failed(PairingOutcome.badInvite) }
        guard let transport = transportFor(invite.address) else { return .failed(PairingOutcome.badInvite) }
        let identity = DeviceIdentity.generate()
        let nonce = PairingExchange.nonce()
        let client = CoreClient(transport: transport, signer: identity.signer, clientID: identity.id)
        let response: [String: Any]
        do { response = try client.pairDevice(PairingExchange.request(invite: invite, label: label, identity: identity, nonce: nonce)) } catch AtlasError.core(let code) {
            return .failed(PairingOutcome.message(forCoreCode: code))
        } catch { return .failed(PairingOutcome.unreachable) }
        guard PairingExchange.verifyCore(invite: invite, identity: identity, nonce: nonce, response: response) else { return .failed(PairingOutcome.impostor) }
        let device = PairedDevice(id: identity.id, keyBytes: identity.signer.rawRepresentation, fingerprint: invite.fingerprint, address: invite.address)
        do { try vault.save(device) } catch { return .failed("Atlas could not keep the pairing safely on this phone.") }
        return .paired(device)
    }
}
