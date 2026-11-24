import Foundation

/// A phone's offline work (Stage 8): edits made without a connection are kept in order, each with an id and the record version it was made against, and sent when the Mac is reachable again. A conflict is
/// shown and never overwritten; replay is safe because the Core answers an id it has already applied as a duplicate.
public struct QueuedOperation: Codable, Equatable {
    public let opID: String
    public let name: String
    public let payload: Data  // JSON, exactly as the Core's action expects it

    public init(opID: String, name: String, payload: Data) { self.opID = opID; self.name = name; self.payload = payload }
}

public protocol BlobStore: AnyObject {
    func load() -> Data?
    /// True only if the bytes are really stored. A store that could not keep them says so; nothing may be reported as saved otherwise.
    @discardableResult func save(_ data: Data) -> Bool
    func erase()
}

public final class MemoryBlob: BlobStore {
    private var data: Data?
    public init() {}
    public func load() -> Data? { data }
    public func save(_ data: Data) -> Bool { self.data = data; return true }
    public func erase() { data = nil }
}

public final class OfflineQueue {
    public static let maxOperations = 500
    /// One operation's payload may be no larger than this, and one request carries no more than `maxBatchBytes` of them, so a request is always inside the Core's and the relay's body cap and the queue always makes progress.
    public static let maxOperationBytes = 16_000
    public static let maxBatchBytes = 48_000
    public private(set) var operations: [QueuedOperation]
    /// True when stored queue bytes exist but cannot be read. The queue then refuses new work and never writes over them, so what the owner saved can still be recovered.
    public private(set) var damaged = false
    private let store: BlobStore

    public init(store: BlobStore) {
        self.store = store
        operations = []
        guard let data = store.load() else { return }
        if let decoded = try? JSONDecoder().decode([QueuedOperation].self, from: data) { operations = decoded } else { damaged = true }
    }

    private func persist() -> Bool {
        guard !damaged, let data = try? JSONEncoder().encode(operations) else { return false }
        return store.save(data)
    }

    /// Only the owner's own-record changes can be queued; anything that needs an approval is not in this vocabulary at all.
    public static func isAllowed(_ name: String) -> Bool {
        let parts = name.split(separator: ".").map(String.init)
        return parts.count == 2 && OwnDomain(rawValue: parts[0]) != nil && ["create", "edit", "archive"].contains(parts[1])
    }

    @discardableResult
    public func enqueue(_ name: String, payload: [String: Any]) -> QueuedOperation? {
        guard !damaged, Self.isAllowed(name), operations.count < Self.maxOperations, let data = try? JSONSerialization.data(withJSONObject: payload), data.count <= Self.maxOperationBytes else { return nil }
        let op = QueuedOperation(opID: "op-" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased(), name: name, payload: data)
        operations.append(op)
        guard persist() else { operations.removeLast(); return nil }  // never reported as saved unless it was
        return op
    }

    public func enqueue(create draft: RecordDraft, now: Date = Date()) -> QueuedOperation? {
        guard let payload = draft.createPayload(id: RecordIdentity.make(domain: draft.domain), now: now) else { return nil }
        return enqueue(draft.domain.createAction, payload: payload)
    }

    public func enqueue(archive record: OwnRecord, in domain: OwnDomain) -> QueuedOperation? {
        enqueue(domain.archiveAction, payload: ["id": record.id, "expected_version": record.version])
    }

    /// The oldest operations that fit one request, in order.
    public func nextBatch() -> [QueuedOperation] {
        var size = 0, batch: [QueuedOperation] = []
        for op in operations {
            size += op.payload.count + op.opID.utf8.count + op.name.utf8.count + 64
            if size > Self.maxBatchBytes && !batch.isEmpty { break }
            batch.append(op)
        }
        return batch
    }

    /// What the Core can be sent.
    public var requestOps: [[String: Any]] { Self.requestOps(of: operations) }

    public static func requestOps(of operations: [QueuedOperation]) -> [[String: Any]] {
        operations.map { ["op_id": $0.opID, "name": $0.name, "payload": (try? JSONSerialization.jsonObject(with: $0.payload)) ?? [:]] }
    }

    func remove(_ ids: Set<String>) {
        let before = operations
        operations.removeAll { ids.contains($0.opID) }
        if !persist() { operations = before }  // the Core has them; if this phone could not record that, they stay and are answered as duplicates next time, never lost
    }

    func clear() { operations = []; store.erase() }
}

public struct SyncConflict: Equatable {
    public let opID: String
    public let currentVersion: Int?
}

public enum SyncOutcome: Equatable {
    case nothingToSend
    case synced(applied: Int, duplicates: Int, conflicts: [SyncConflict], rejected: Int)
    case offline
    case revoked
    case failed(String)

    /// One plain sentence for the owner.
    public var message: String {
        switch self {
        case .nothingToSend: return "Everything is up to date."
        case .synced(let applied, _, let conflicts, let rejected):
            var parts = ["\(applied) \(applied == 1 ? "change" : "changes") sent to your Mac."]
            if !conflicts.isEmpty { parts.append("\(conflicts.count) could not be applied because it was changed on your Mac first. Nothing was overwritten.") }
            if rejected > 0 { parts.append("\(rejected) \(rejected == 1 ? "was" : "were") not allowed.") }
            return parts.joined(separator: " ")
        case .offline: return "Your Mac cannot be reached. Your changes are saved and will be sent when it can."
        case .revoked: return "This phone is no longer paired with your Mac. Pair it again to continue."
        case .failed(let text): return text
        }
    }
}

public enum SyncResults {
    public static func interpret(_ response: [String: Any]) -> SyncOutcome {
        guard let rows = response["results"] as? [[String: Any]] else { return .failed("Atlas could not read your Mac's answer.") }
        var applied = 0, duplicates = 0, rejected = 0
        var conflicts: [SyncConflict] = []
        for row in rows {
            switch row["status"] as? String ?? "" {
            case "applied": applied += 1
            case "duplicate": duplicates += 1
            case "conflict": conflicts.append(SyncConflict(opID: row["op_id"] as? String ?? "", currentVersion: row["current_version"] as? Int))
            default: rejected += 1
            }
        }
        return .synced(applied: applied, duplicates: duplicates, conflicts: conflicts, rejected: rejected)
    }

    /// Every operation the Core answered is finished (a conflict is final for its id; the owner resolves it with a new edit), so all of them leave the queue.
    public static func answered(_ response: [String: Any]) -> Set<String> {
        Set((response["results"] as? [[String: Any]] ?? []).compactMap { $0["op_id"] as? String })
    }

    /// A device the Core no longer knows or that was revoked has every operation rejected with `device_not_allowed`.
    public static func isRevoked(_ response: [String: Any]) -> Bool {
        let rows = response["results"] as? [[String: Any]] ?? []
        return !rows.isEmpty && rows.allSatisfy { ($0["status"] as? String) == "rejected" && ($0["code"] as? String) == "device_not_allowed" }
    }
}

/// What the phone may keep to read offline: only the owner's own records, for a limited time; wiped if the pairing ends.
public struct CachedRecords: Codable, Equatable {
    public static let timeToLive: TimeInterval = 7 * 24 * 3600
    public struct Row: Codable, Equatable { public let id: String; public let title: String; public let date: String; public let version: Int; public let fields: [String: String] }

    public let fetchedAt: Date
    public let rows: [Row]

    public func isExpired(now: Date) -> Bool { now.timeIntervalSince(fetchedAt) > Self.timeToLive }
    public func records() -> [OwnRecord] { rows.map { OwnRecord(id: $0.id, title: $0.title, date: $0.date, version: $0.version, fields: $0.fields) } }
}
