import Foundation

/// The owner's own Calendar, Contacts, Notes and Travel (UI/UX specification 4.6: views over shared Atlas context, shown only when the Core can serve them).
public enum OwnDomain: String, CaseIterable {
    case calendar, contacts, notes, travel

    public var title: String {
        switch self {
        case .calendar: return "Calendar"
        case .contacts: return "Contacts"
        case .notes: return "Notes"
        case .travel: return "Travel"
        }
    }

    public var symbol: String {
        switch self {
        case .calendar: return "calendar"
        case .contacts: return "person.crop.circle"
        case .notes: return "note.text"
        case .travel: return "airplane"
        }
    }

    /// Calendar events and trips have a start and an optional end.
    public var hasDates: Bool { self == .calendar || self == .travel }

    public var createAction: String { rawValue + ".create" }
    public var editAction: String { rawValue + ".edit" }
    public var archiveAction: String { rawValue + ".archive" }

    public init?(areaTitle: String) {
        guard let match = OwnDomain.allCases.first(where: { $0.title == areaTitle }) else { return nil }
        self = match
    }

    /// The short sentence under the title: what this area is for and the next useful step.
    public var emptyText: String {
        switch self {
        case .calendar: return "No events yet. Add one, and Atlas will tell you when two of them overlap."
        case .contacts: return "No contacts yet. Add the people you want Atlas to know about."
        case .notes: return "No notes yet. Add a note and Atlas can find it later."
        case .travel: return "No trips yet. Add one with its dates and booking, and keep it all in one place."
        }
    }
}

public struct OwnRecord: Identifiable, Equatable {
    public let id: String
    public let title: String
    public let date: String
    public let version: Int
    public let fields: [String: String]

    /// One plain line of detail for a row, from the fields that matter for the domain.
    public func detail(for domain: OwnDomain) -> String {
        switch domain {
        case .calendar: return [fields["starts"], fields["location"]].compactMap { $0 }.joined(separator: " · ")
        case .contacts: return [fields["organisation"], fields["phone"], fields["email"]].compactMap { $0 }.joined(separator: " · ")
        case .notes: return fields["text"] ?? ""
        case .travel: return [fields["starts"], fields["booking"]].compactMap { $0 }.joined(separator: " · ")
        }
    }
}

public enum RecordsOutcome {
    public static func from(_ response: [String: Any]) -> LoadState<[OwnRecord]> {
        guard let rows = response["records"] as? [[String: Any]] else { return .unavailable(.unknownState) }
        let records: [OwnRecord] = rows.compactMap { row in
            guard let id = row["id"] as? String, let title = row["title"] as? String, let date = row["date"] as? String, let version = row["version"] as? Int else { return nil }
            let fields = (row["fields"] as? [String: Any] ?? [:]).compactMapValues { $0 as? String }
            return OwnRecord(id: id, title: title, date: date, version: version, fields: fields)
        }
        return records.isEmpty ? .empty : .loaded(records)
    }
}

/// What the owner typed to add something. Validation says what is wrong in plain words; the payload is exactly what the Core's action expects.
public struct RecordDraft: Equatable {
    public var domain: OwnDomain
    public var title = ""
    public var text = ""  // a note's text
    public var starts: Date?
    public var ends: Date?
    public var location = ""
    public var booking = ""
    public var phone = ""
    public var email = ""

    public init(domain: OwnDomain) { self.domain = domain }

    private static func iso(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }

    public func problem() -> String? {
        if title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return domain == .contacts ? "Enter a name." : (domain == .travel ? "Enter where you are going." : "Enter a title.") }
        switch domain {
        case .notes: return text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "Write the note." : nil
        case .calendar, .travel:
            guard let starts else { return "Choose when it starts." }
            if let ends, ends < starts { return "The end cannot be before the start." }
            return nil
        case .contacts: return nil
        }
    }

    /// The payload of the create action, or nil while the draft has a problem.
    public func createPayload(id: String, now: Date) -> [String: Any]? {
        guard problem() == nil else { return nil }
        let name = title.trimmingCharacters(in: .whitespacesAndNewlines)
        switch domain {
        case .notes: return ["id": id, "date": Self.iso(now), "title": name, "fields": ["text": text]]
        case .calendar, .travel:
            guard let starts else { return nil }
            var fields: [String: String] = ["starts": Self.iso(starts)]
            if let ends { fields["ends"] = Self.iso(ends) }
            if domain == .calendar, !location.isEmpty { fields["location"] = location }
            if domain == .travel, !booking.isEmpty { fields["booking"] = booking }
            return ["id": id, "date": Self.iso(starts), "title": name, "fields": fields]
        case .contacts:
            var fields: [String: String] = ["name": name]
            if !phone.isEmpty { fields["phone"] = phone }
            if !email.isEmpty { fields["email"] = email }
            return ["id": id, "date": Self.iso(now), "title": name, "fields": fields]
        }
    }
}

public enum RecordIdentity {
    /// A new, readable, unique id the Core accepts (`[A-Za-z0-9._-]{1,120}`).
    public static func make(domain: OwnDomain, uuid: UUID = UUID()) -> String { domain.rawValue + "-" + uuid.uuidString.lowercased() }
}
