import Foundation

/// One chronological surface for tasks, updates, risks, decisions and actions (UI/UX specification 4.7). Only real events appear; nothing is invented to fill the space.
public struct ActivityItem: Identifiable, Equatable {
    public enum Kind: Equatable { case task, update, risk, decision, action }

    public let id: String
    public let kind: Kind
    public let title: String
    public let detail: String
    public let date: Date
    public let needsAttention: Bool
    /// Items with the same key are one event (a notification and the task it came from must not appear twice).
    public let dedupeKey: String

    public init(id: String, kind: Kind, title: String, detail: String, date: Date, needsAttention: Bool = false, dedupeKey: String? = nil) {
        self.id = id; self.kind = kind; self.title = title; self.detail = detail; self.date = date; self.needsAttention = needsAttention; self.dedupeKey = dedupeKey ?? id
    }

    /// The symbol that goes with the label (status never relies on colour alone).
    public var symbol: String {
        switch kind {
        case .task: return "text.bubble"
        case .update: return "arrow.triangle.2.circlepath"
        case .risk: return "exclamationmark.triangle"
        case .decision: return "questionmark.circle"
        case .action: return "bolt.circle"
        }
    }
}

public enum ActivityFeed {
    /// Newest first, one item per event (the most recent of any duplicates is kept).
    public static func merged(_ items: [ActivityItem]) -> [ActivityItem] {
        var best: [String: ActivityItem] = [:]
        for item in items {
            if let existing = best[item.dedupeKey], existing.date >= item.date { continue }
            best[item.dedupeKey] = item
        }
        return best.values.sorted { $0.date == $1.date ? $0.id < $1.id : $0.date > $1.date }
    }

    /// "Needs your attention": only material items, hidden when there are none.
    public static func needingAttention(_ items: [ActivityItem]) -> [ActivityItem] { merged(items).filter { $0.needsAttention } }

    /// The home surface's "Continue where you left off": a small number of recent tasks.
    public static func recentTasks(_ items: [ActivityItem], limit: Int = 3) -> [ActivityItem] { Array(merged(items).filter { $0.kind == .task }.prefix(limit)) }
}

/// The greeting on Home: used only when the local time is known.
public enum Greeting {
    public static func text(hour: Int?) -> String {
        guard let hour, (0...23).contains(hour) else { return "Your Atlas" }
        switch hour {
        case 5..<12: return "Good morning"
        case 12..<18: return "Good afternoon"
        default: return "Good evening"
        }
    }
}

extension ActivityItem {
    /// An item for "Needs your attention" from the Core's attention list. A kind this app does not know is not shown (never as raw text).
    public static func fromAttention(_ raw: [String: Any], now: Date) -> ActivityItem? {
        guard (raw["kind"] as? String) == "calendar_conflict", let key = raw["key"] as? String, let detail = raw["title"] as? String else { return nil }
        return ActivityItem(id: "attention-" + key, kind: .risk, title: "Two events overlap", detail: detail, date: now, needsAttention: true, dedupeKey: key)
    }
}
