import Foundation

/// Everything the phone app does that is not drawing: it holds the pairing, reads the owner's own records (from the Mac when it can, from a short-lived cache when it cannot), queues edits offline, syncs them,
/// and asks questions. The screens only show what this reports. A revoked or unpaired phone wipes its cache and queue and says so.
public final class PhoneEngine {
    public enum Link: Equatable { case notPaired, online, offline, revoked }

    private let vault: DeviceVault
    private let queue: OfflineQueue
    private let cacheFor: (OwnDomain) -> BlobStore
    private let transportFor: (String) -> (any HTTPTransport)?
    private let clock: () -> Date
    public private(set) var link: Link

    public init(vault: DeviceVault, queueStore: BlobStore, cacheFor: @escaping (OwnDomain) -> BlobStore, transportFor: @escaping (String) -> (any HTTPTransport)?, clock: @escaping () -> Date = Date.init) {
        self.vault = vault; self.queue = OfflineQueue(store: queueStore); self.cacheFor = cacheFor; self.transportFor = transportFor; self.clock = clock
        link = vault.load() == nil ? .notPaired : .online
    }

    public var pendingChanges: Int { queue.operations.count }
    public var isPaired: Bool { vault.load() != nil }

    private func client() -> CoreClient? {
        guard let device = vault.load(), let identity = device.identity, let transport = transportFor(device.address) else { return nil }
        return CoreClient(transport: transport, signer: identity.signingKey, clientID: identity.id)
    }

    // MARK: pairing

    public func pair(inviteText: String, label: String) -> PairingOutcome {
        let outcome = DevicePairing.pair(inviteText: inviteText, label: label, vault: vault, transportFor: transportFor)
        if case .paired = outcome { link = .online }
        return outcome
    }

    /// Forget the pairing on this phone: the key, the queue and everything cached are erased.
    public func unpair() {
        vault.erase()
        queue.clear()
        for domain in OwnDomain.allCases { cacheFor(domain).erase() }
        link = .notPaired
    }

    private func revokedHere() { unpair(); link = .revoked }

    // MARK: reading

    public struct Reading { public let state: LoadState<[OwnRecord]>; public let fromCache: Bool; public let fetchedAt: Date? }

    /// The records of one area: from the Mac if it answers, otherwise from the cache if it is still fresh, otherwise nothing, and it says which.
    public func records(_ domain: OwnDomain) -> Reading {
        guard let client = client() else { return Reading(state: .unavailable(.coreUnreachable), fromCache: false, fetchedAt: nil) }
        let name = domain.rawValue
        do {
            let response = try client.records(name)
            link = .online
            let state = RecordsOutcome.from(response)
            if case .loaded(let records) = state { remember(records, domain) } else { cacheFor(domain).erase() }
            return Reading(state: state, fromCache: false, fetchedAt: clock())
        } catch AtlasError.core(let code) where code == "forbidden" || code == "unauthenticated" {
            revokedHere()
            return Reading(state: .denied(SyncOutcome.revoked.message), fromCache: false, fetchedAt: nil)
        } catch {
            link = .offline
            if let data = cacheFor(domain).load(), let cached = try? JSONDecoder.iso.decode(CachedRecords.self, from: data), !cached.isExpired(now: clock()) {
                let rows = cached.records()
                return Reading(state: rows.isEmpty ? .empty : .partial(rows, note: "Saved on this phone. Your Mac cannot be reached."), fromCache: true, fetchedAt: cached.fetchedAt)
            }
            return Reading(state: .unavailable(.coreUnreachable), fromCache: false, fetchedAt: nil)
        }
    }

    private func remember(_ records: [OwnRecord], _ domain: OwnDomain) {
        let rows = records.map { CachedRecords.Row(id: $0.id, title: $0.title, date: $0.date, version: $0.version, fields: $0.fields) }
        if let data = try? JSONEncoder.iso.encode(CachedRecords(fetchedAt: clock(), rows: rows)) { cacheFor(domain).save(data) }
    }

    // MARK: editing offline

    /// Adds something. It is queued first (so nothing is lost if the Mac is away) and then sent if it can be.
    @discardableResult
    public func add(_ draft: RecordDraft) -> SyncOutcome {
        guard queue.enqueue(create: draft, now: clock()) != nil else { return .failed(draft.problem() ?? "Atlas could not save that.") }
        return sync()
    }

    @discardableResult
    public func archive(_ record: OwnRecord, in domain: OwnDomain) -> SyncOutcome {
        guard queue.enqueue(archive: record, in: domain) != nil else { return .failed("Atlas could not save that.") }
        return sync()
    }

    @discardableResult
    public func sync() -> SyncOutcome {
        guard !queue.operations.isEmpty else { return .nothingToSend }
        guard let client = client() else { return .offline }
        do {
            let response = try client.sync(ops: queue.requestOps)
            if SyncResults.isRevoked(response) { revokedHere(); return .revoked }
            link = .online
            queue.remove(SyncResults.answered(response))
            return SyncResults.interpret(response)
        } catch AtlasError.core(let code) where code == "forbidden" || code == "unauthenticated" {
            revokedHere()
            return .revoked
        } catch {
            link = .offline
            return .offline  // the changes stay queued
        }
    }

    // MARK: asking

    /// Questions need the Mac: its model, its sources and its rules. Without it the phone says so instead of guessing.
    public func ask(_ question: String, scope: [String]) -> Result<String, AtlasError> {
        guard let client = client() else { return .failure(.local("not paired")) }
        do {
            let id = try client.ask(question: question, scope: scope)
            link = .online
            return .success(id)
        } catch let error as AtlasError {
            if case .core(let code) = error, code == "forbidden" || code == "unauthenticated" { revokedHere() } else if case .local = error { link = .offline }
            return .failure(error)
        } catch { return .failure(.local("unreachable")) }
    }

    public func taskClient() -> CoreClient? { client() }
}

extension JSONEncoder {
    static var iso: JSONEncoder { let e = JSONEncoder(); e.dateEncodingStrategy = .iso8601; return e }
}

extension JSONDecoder {
    static var iso: JSONDecoder { let d = JSONDecoder(); d.dateDecodingStrategy = .iso8601; return d }
}
