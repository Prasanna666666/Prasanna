import Foundation

/// Which notifications the app may show (UI/UX specification 4.7 and 9): opt-in, material, deduplicated, and content-free by default so a lock screen or another device learns nothing private.
public struct NotificationPlan: Equatable {
    public let id: String
    public let title: String
    public let body: String
}

public enum NotificationPlanner {
    public static let maxPerRound = 3
    public static let genericBody = "Something needs your attention. Open Atlas to see what."

    /// Plans for items that need attention and have not been notified yet. Nothing at all unless the owner turned notifications on.
    public static func plans(for items: [ActivityItem], alreadyNotified: Set<String>, enabled: Bool) -> [NotificationPlan] {
        guard enabled else { return [] }
        var seen = alreadyNotified
        var out: [NotificationPlan] = []
        for item in ActivityFeed.needingAttention(items) where !seen.contains(item.dedupeKey) {
            seen.insert(item.dedupeKey)
            out.append(NotificationPlan(id: item.dedupeKey, title: "Atlas", body: genericBody))
            if out.count == maxPerRound { break }
        }
        return out
    }
}
