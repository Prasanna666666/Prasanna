import Foundation

/// The Library surface (UI/UX specification 4.5): search across what the owner enabled, with an honest difference between "no match", "not read yet" and "not allowed".
public struct LibraryResult: Identifiable, Equatable {
    public let id: String
    public let sourceType: String
    public let kind: String  // the source type in plain words
    public let title: String
    public let excerpt: String
    public let place: String  // where in the source, in human words
}

public struct LibraryPage: Equatable {
    public let results: [LibraryResult]
    public let coverageLine: String?
    public var types: [String] { Array(Set(results.map { $0.sourceType })).sorted() }
}

public enum LibrarySort: String, CaseIterable {
    case bestMatch = "Best match"
    case title = "Title"

    /// Explicit, stable ordering: best match keeps the Core's order; title is alphabetical with the Core's order breaking ties.
    public func apply(_ results: [LibraryResult]) -> [LibraryResult] {
        switch self {
        case .bestMatch: return results
        case .title:
            return results.enumerated().sorted { a, b in
                let order = a.element.title.localizedCaseInsensitiveCompare(b.element.title)
                return order == .orderedSame ? a.offset < b.offset : order == .orderedAscending
            }.map { $0.element }
        }
    }
}

public enum LibraryOutcome {
    /// Turns the Core's answer into a state the screen can always show. An unknown state fails safe into an "unavailable" notice.
    public static func from(_ response: [String: Any], catalogue c: Catalogue = .shared) -> LoadState<LibraryPage> {
        let state = response["state"] as? String ?? ""
        let coverage = response["coverage"] as? [[String: Any]] ?? []
        let line = coverageLine(coverage, c)
        let results: [LibraryResult] = (response["results"] as? [[String: Any]] ?? []).compactMap { r in
            guard let id = r["source_id"] as? String, let type = r["source_type"] as? String else { return nil }
            var place = c.locatorKinds[r["locator_kind"] as? String ?? ""] ?? c.locatorKinds["span_only"] ?? ""
            if place.contains("{") { place = c.locatorKinds["span_only"] ?? "" }
            return LibraryResult(id: id, sourceType: type, kind: c.sourceKinds[type] ?? type, title: (r["title"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? (c.sourceKinds[type] ?? type), excerpt: r["excerpt"] as? String ?? "", place: place)
        }
        let page = LibraryPage(results: results, coverageLine: line)
        switch state {
        case "results": return .loaded(page)
        case "no_results": return .empty
        case "partial": return .partial(page, note: "Atlas is still reading some sources, so more matches may appear. " + (line ?? ""))
        case "partial_no_results": return .partial(page, note: "No matches yet. Atlas is still reading some sources, so a match may appear later. " + (line ?? ""))
        case "denied": return .denied("Atlas is not allowed to search that. Turn on a source in Settings.")
        default: return .unavailable(.unknownState)
        }
    }

    static func coverageLine(_ coverage: [[String: Any]], _ c: Catalogue) -> String? {
        let parts: [String] = coverage.compactMap { entry in
            guard let type = entry["source_type"] as? String, let total = entry["total"] as? Int, let searched = entry["searched"] as? Int else { return nil }
            return "\(c.sourceKinds[type] ?? type): read \(searched) of \(total)."
        }
        return parts.isEmpty ? nil : parts.joined(separator: " ")
    }
}
