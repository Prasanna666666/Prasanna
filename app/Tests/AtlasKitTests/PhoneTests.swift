import CryptoKit
import XCTest
@testable import AtlasKit

/// A transport that can be switched off, to stand in for a phone with no connection.
final class SwitchableTransport: HTTPTransport {
    var up = true
    let inner: any HTTPTransport
    init(_ inner: any HTTPTransport) { self.inner = inner }
    func send(method: String, target: String, headers: [String: String], body: Data) throws -> UnixHTTP.Response {
        guard up else { throw AtlasError.local("no connection") }
        return try inner.send(method: method, target: target, headers: headers, body: body)
    }
}

final class PairingLogicTests: XCTestCase {
    private let fingerprint = String(repeating: "ab", count: 32)

    func testAnInviteIsReadOnlyIfEveryPartIsWellFormedAndTheAddressIsSafe() {
        let good = PairingInvite(code: "code-12345678", fingerprint: fingerprint, address: "https://mac.example.invalid")
        XCTAssertEqual(PairingInvite.parse(good.text), good)
        XCTAssertNil(PairingInvite.parse("atlas://pair?code=short&fp=\(fingerprint)&addr=https://mac.example.invalid"))
        XCTAssertNil(PairingInvite.parse("atlas://pair?code=code-12345678&fp=nothex&addr=https://mac.example.invalid"))
        XCTAssertNil(PairingInvite.parse("atlas://pair?code=code-12345678&fp=\(fingerprint)&addr=http://api.example.com"), "plain http to the Internet is not an address")
        XCTAssertNotNil(PairingInvite.parse("atlas://pair?code=code-12345678&fp=\(fingerprint)&addr=http://192.168.1.20:8443"))
        XCTAssertNil(PairingInvite.parse("https://pair?code=code-12345678"))
        XCTAssertNil(PairingInvite.parse("not an invite"))
    }

    func testTheMacShowsAnInviteOnlyForAnAddressAPhoneWouldAcceptAndOnlyFromARealOffer() {
        let offer: [String: Any] = ["code": "code-12345678", "core_fingerprint": fingerprint, "expires_at": "2026-12-01T10:00:00Z"]
        XCTAssertEqual(PairingInvite.make(offer: offer, address: " https://mac.example.invalid ")?.address, "https://mac.example.invalid")
        XCTAssertNil(PairingInvite.make(offer: offer, address: "http://api.example.com"))
        XCTAssertNil(PairingInvite.make(offer: offer, address: ""))
        XCTAssertNil(PairingInvite.make(offer: ["code": "x"], address: "https://mac.example.invalid"))
    }

    func testTheDeviceAcceptsOnlyTheCoreWhoseKeyMatchesTheFingerprintAndWhoSignedItsKeyAndNonce() {
        let core = Curve25519.Signing.PrivateKey()
        let fp = SHA256.hash(data: core.publicKey.rawRepresentation).map { String(format: "%02x", $0) }.joined()
        let invite = PairingInvite(code: "code-12345678", fingerprint: fp, address: "https://mac.example.invalid")
        let identity = DeviceIdentity.generate()
        let nonce = PairingExchange.nonce()
        func answer(_ signer: Curve25519.Signing.PrivateKey, nonce: String) -> [String: Any] {
            let proof = try! signer.signature(for: identity.signingKey.publicKey.rawRepresentation + Data(nonce.utf8))
            return ["core_public_key": signer.publicKey.rawRepresentation.base64EncodedString(), "proof": proof.base64EncodedString()]
        }
        XCTAssertTrue(PairingExchange.verifyCore(invite: invite, identity: identity, nonce: nonce, response: answer(core, nonce: nonce)))
        XCTAssertFalse(PairingExchange.verifyCore(invite: invite, identity: identity, nonce: nonce, response: answer(Curve25519.Signing.PrivateKey(), nonce: nonce)), "an impostor's key does not match the pinned fingerprint")
        XCTAssertFalse(PairingExchange.verifyCore(invite: invite, identity: identity, nonce: nonce, response: answer(core, nonce: "another-nonce")), "a proof for another pairing is refused")
        XCTAssertFalse(PairingExchange.verifyCore(invite: invite, identity: identity, nonce: nonce, response: [:]))
    }

    func testTheQueueKeepsOnlyOwnRecordChangesInOrderAndSurvivesARestart() {
        let blob = MemoryBlob()
        let queue = OfflineQueue(store: blob)
        XCTAssertNil(queue.enqueue("finance.create", payload: [:]), "Finance is not in the vocabulary")
        XCTAssertNil(queue.enqueue("actions.approve", payload: [:]), "an approval can never be queued")
        var draft = RecordDraft(domain: .notes)
        draft.title = "Passport"; draft.text = "Renew it."
        let first = queue.enqueue(create: draft)
        let second = queue.enqueue(OwnDomain.notes.archiveAction, payload: ["id": "n1", "expected_version": 1])
        XCTAssertEqual(queue.operations.map { $0.opID }, [first!.opID, second!.opID])
        XCTAssertEqual(OfflineQueue(store: blob).operations, queue.operations)  // a restart keeps them
        XCTAssertTrue(first!.opID.range(of: "^[A-Za-z0-9_-]{8,64}$", options: .regularExpression) != nil)
    }

    func testSyncAnswersAreReadInPlainWordsAndARevokedPhoneIsRecognised() {
        let mixed: [String: Any] = ["results": [["op_id": "a", "status": "applied"], ["op_id": "b", "status": "duplicate"], ["op_id": "c", "status": "conflict", "current_version": 3], ["op_id": "d", "status": "rejected", "code": "operation_not_allowed"]]]
        XCTAssertEqual(SyncResults.interpret(mixed), .synced(applied: 1, duplicates: 1, conflicts: [SyncConflict(opID: "c", currentVersion: 3)], rejected: 1))
        XCTAssertEqual(SyncResults.answered(mixed), ["a", "b", "c", "d"])
        XCTAssertTrue(SyncOutcome.synced(applied: 1, duplicates: 0, conflicts: [SyncConflict(opID: "c", currentVersion: 3)], rejected: 0).message.contains("Nothing was overwritten"))
        XCTAssertFalse(SyncResults.isRevoked(mixed))
        XCTAssertTrue(SyncResults.isRevoked(["results": [["op_id": "a", "status": "rejected", "code": "device_not_allowed"]]]))
        XCTAssertTrue(SyncOutcome.offline.message.contains("saved"))
    }

    func testTheCacheExpiresAfterAWeek() {
        let cached = CachedRecords(fetchedAt: Date(timeIntervalSince1970: 0), rows: [])
        XCTAssertFalse(cached.isExpired(now: Date(timeIntervalSince1970: 6 * 24 * 3600)))
        XCTAssertTrue(cached.isExpired(now: Date(timeIntervalSince1970: 8 * 24 * 3600)))
    }
}

/// The phone engine against the real Core: pairing with a pinned key, reading, working offline, syncing, a conflict, and revocation. Needs `ATLAS_CI_PYTHON` (set by the CI `macos` job).
final class PhoneEngineEndToEndTests: XCTestCase {
    private let services = ["task-store", "designation-store", "documents-index", "mail-index", "edits-store", "finance-records", "finance-index", "health-records", "health-index", "calendar-index", "contacts-index", "notes-index", "photos-index", "model-record"].map { "atlas-\($0)" } + ["atlas-designation-anchor"]

    private func deleteKeychainItems() {
        for service in services {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: "/usr/bin/security")
            p.arguments = ["delete-generic-password", "-s", service]
            p.standardOutput = FileHandle.nullDevice
            p.standardError = FileHandle.nullDevice
            try? p.run()
            p.waitUntilExit()
        }
    }

    func testAPhonePairsReadsOfflineSyncsHandlesAConflictAndIsWipedWhenRevoked() throws {
        let environment = ProcessInfo.processInfo.environment
        if environment["CI"] != nil { XCTAssertNotNil(environment["ATLAS_CI_PYTHON"], "on CI this test must run, not be skipped") }
        guard let python = environment["ATLAS_CI_PYTHON"] else { throw XCTSkip("ATLAS_CI_PYTHON is not set") }
        let base = URL(fileURLWithPath: "/tmp/atl" + UUID().uuidString.prefix(8).lowercased())
        let socket = base.appendingPathComponent("run/core.sock").path
        try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
        deleteKeychainItems()
        let launcher = CoreLauncher(executable: URL(fileURLWithPath: python), arguments: ["-m", "atlas_core.serve"])
        defer { launcher.stop(); deleteKeychainItems(); try? FileManager.default.removeItem(at: base) }
        try launcher.start(dataDir: base.appendingPathComponent("core").path, socket: socket)

        let owner = CoreClient(socketPath: socket, signer: Curve25519.Signing.PrivateKey(), clientID: "owner-phone-ci-0001")
        try owner.enrolSelf(bootstrapCode: try XCTUnwrap(launcher.bootstrapCode))
        _ = try owner.act("notes.create", payload: ["id": "note-passport", "date": "2026-10-18T00:00:00Z", "title": "Passport", "fields": ["text": "Renew it."]])

        let link = SwitchableTransport(UnixHTTP(path: socket))
        let vault = MemoryVault()
        let queue = MemoryBlob()
        var caches: [OwnDomain: MemoryBlob] = [:]
        let phone = PhoneEngine(vault: vault, queueStore: queue, cacheFor: { domain in caches[domain] ?? { let b = MemoryBlob(); caches[domain] = b; return b }() }, transportFor: { _ in link })
        XCTAssertEqual(phone.link, .notPaired)

        // pairing: a stranger's code, a stolen-looking invite and an impostor's fingerprint all fail; the real one works
        let offer = try owner.openPairingOffer()
        let code = try XCTUnwrap(offer["code"] as? String), fingerprint = try XCTUnwrap(offer["core_fingerprint"] as? String)
        XCTAssertEqual(phone.pair(inviteText: "nonsense", label: "My phone"), .failed(PairingOutcome.badInvite))
        let wrong = PairingInvite(code: "wrong-code-1234", fingerprint: fingerprint, address: "https://mac.example.invalid").text
        XCTAssertEqual(phone.pair(inviteText: wrong, label: "My phone"), .failed(PairingOutcome.message(forCoreCode: "forbidden")))
        XCTAssertFalse(phone.isPaired)
        let impostor = PairingInvite(code: code, fingerprint: String(repeating: "0", count: 64), address: "https://mac.example.invalid").text
        XCTAssertEqual(phone.pair(inviteText: impostor, label: "My phone"), .failed(PairingOutcome.impostor))
        XCTAssertFalse(phone.isPaired, "nothing is kept when the Core could not prove itself")
        let second = try owner.openPairingOffer()
        let invite = PairingInvite(code: try XCTUnwrap(second["code"] as? String), fingerprint: fingerprint, address: "https://mac.example.invalid").text
        guard case .paired(let device) = phone.pair(inviteText: invite, label: "My phone") else { return XCTFail("pairing should work") }
        XCTAssertTrue(phone.isPaired)
        XCTAssertEqual(phone.link, .online)
        XCTAssertTrue((try owner.devices()).contains { ($0["device_id"] as? String) == device.id })

        // reading, online and then offline from the cache
        let online = phone.records(.notes)
        guard case .loaded(let rows) = online.state else { return XCTFail("expected the note") }
        XCTAssertEqual(rows.map { $0.title }, ["Passport"])
        XCTAssertFalse(online.fromCache)
        link.up = false
        let offline = phone.records(.notes)
        XCTAssertTrue(offline.fromCache)
        guard case .partial(let cachedRows, let note) = offline.state else { return XCTFail("expected the cached note") }
        XCTAssertEqual(cachedRows.map { $0.title }, ["Passport"])
        XCTAssertTrue(note.contains("Saved on this phone"))
        XCTAssertEqual(phone.link, .offline)
        XCTAssertEqual({ if case .unavailable = phone.records(.travel).state { return true } else { return false } }(), true, "nothing was cached for Travel, and it says so")

        // adding offline keeps the change, then it goes through when the Mac is back
        var draft = RecordDraft(domain: .notes)
        draft.title = "Offline idea"; draft.text = "Written on a train."
        XCTAssertEqual(phone.add(draft), .offline)
        XCTAssertEqual(phone.pendingChanges, 1)
        link.up = true
        XCTAssertEqual(phone.sync(), .synced(applied: 1, duplicates: 0, conflicts: [], rejected: 0))
        XCTAssertEqual(phone.pendingChanges, 0)
        XCTAssertEqual(phone.sync(), .nothingToSend)
        guard case .loaded(let ownerRows) = RecordsOutcome.from(try owner.records("notes")) else { return XCTFail() }
        XCTAssertEqual(Set(ownerRows.map { $0.title }), ["Passport", "Offline idea"])

        // a conflict: the Mac changed the note after the phone last read it, so archiving the old version is reported, not applied
        _ = phone.records(.notes)
        let stale = try XCTUnwrap({ () -> OwnRecord? in if case .loaded(let r) = phone.records(.notes).state { return r.first { $0.title == "Passport" } } else { return nil } }())
        _ = try owner.act("notes.edit", payload: ["id": stale.id, "expected_version": stale.version, "fields": ["text": "Renewed."]])
        guard case .synced(let applied, _, let conflicts, _) = phone.archive(stale, in: .notes) else { return XCTFail("expected a sync result") }
        XCTAssertEqual(applied, 0)
        XCTAssertEqual(conflicts.count, 1)
        XCTAssertNotNil(conflicts.first?.currentVersion)
        guard case .loaded(let after) = RecordsOutcome.from(try owner.records("notes")) else { return XCTFail() }
        XCTAssertTrue(after.contains { $0.title == "Passport" }, "the conflicting archive did not overwrite anything")

        // revocation: the next contact wipes the phone
        XCTAssertTrue(try owner.revokeDevice(device.id))
        _ = phone.records(.notes)
        XCTAssertEqual(phone.link, .revoked)
        XCTAssertFalse(phone.isPaired)
        XCTAssertNil(caches[.notes]?.load(), "the cache is erased when the pairing ends")
        XCTAssertEqual(phone.pendingChanges, 0)
    }
}
