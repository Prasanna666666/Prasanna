import Foundation

/// The owner's review (Home): the Core's orchestrator over fixed code agents for calendar, finance and health. Each area says what it found, or plainly that it is off, empty or not offered. Nothing here
/// computes anything; the text and figures are the Core's.
public struct ReviewView: Equatable {
    public struct Section: Equatable, Identifiable {
        public let id: String
        public let title: String
        public let summary: String
        public let needsAction: Bool  // an area that is off: the owner can turn it on
        public let taskID: String?  // highlights: the task whose verified, cited answer is shown below
    }

    public let sections: [Section]
    public let note: String?
}

public enum ReviewOutcome {
    private static func title(_ area: String) -> String {
        switch area {
        case "calendar": return "Calendar"
        case "highlights": return "Highlights"
        default: return SourceNames.title(area)
        }
    }

    public static func from(_ response: [String: Any]) -> LoadState<ReviewView> {
        guard let status = response["status"] as? String, let rows = response["sections"] as? [[String: Any]] else { return .unavailable(.unknownState) }
        let sections = rows.compactMap { row -> ReviewView.Section? in
            guard let area = row["area"] as? String, let state = row["state"] as? String, let summary = row["summary"] as? String else { return nil }
            return ReviewView.Section(id: area, title: title(area), summary: summary, needsAction: state == "denied" && area != "highlights" && area != "calendar", taskID: row["task_id"] as? String)
        }
        if sections.isEmpty { return .unavailable(.unknownState) }
        let note: String? = status == "completed" ? nil : "Part of the review could not be completed, so it may be missing something."
        return .loaded(ReviewView(sections: sections, note: note))
    }
}
