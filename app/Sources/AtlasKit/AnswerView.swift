import Foundation

public struct CitationView: Identifiable { public let id: Int; public let label: String; public let quote: String? }

/// What a screen prints for an answer: plain words from the catalogue, never a code, path or raw JSON.
public struct AnswerView {
    public let text: String, trust: String, modelLine: String, coverageLine: String?, notices: [String], notSearched: [String], citations: [CitationView]
    /// The source types this answer cites (Core names): what a withdrawal of access must take it off the screen for (MAC-20).
    public let sourceTypes: Set<String>

    public init(_ answer: [String: Any], catalogue c: Catalogue = .shared) {
        text = answer["answer"] as? String ?? ""
        let verification = (answer["verification"] as? [String: Any])?["status"] as? String ?? "unverified"
        trust = c.verification[verification] ?? ""
        if let model = answer["model"] as? [String: Any], let id = model["model_id"] as? String {
            let role = model["role"] as? String ?? ""
            modelLine = c.modelLine.replacingOccurrences(of: "{model_id}", with: id).replacingOccurrences(of: "{role}", with: c.modelRoles[role] ?? role)
        } else { modelLine = c.modelLineUnknown }
        if let coverage = answer["coverage"] as? [String: Any], let state = coverage["state"] as? String {
            let searched = coverage["searched"] as? Int ?? 0
            let line = (coverage["total"] as? Int).map { c.coverageLine.replacingOccurrences(of: "{searched}", with: "\(searched)").replacingOccurrences(of: "{total}", with: "\($0)") }
                ?? c.coverageLineUnknownTotal.replacingOccurrences(of: "{searched}", with: "\(searched)")
            coverageLine = "\(c.coverageState[state] ?? "") \(line)"
        } else { coverageLine = nil }
        notices = (answer["limitations"] as? [String] ?? []).compactMap { c.limitations[$0] }
        notSearched = (answer["not_searched"] as? [[String: Any]] ?? []).map { n in
            let kind = c.sourceKinds[n["source_type"] as? String ?? ""] ?? (n["source_type"] as? String ?? "")
            return "\(kind): \(c.notSearchedReasons[n["reason_code"] as? String ?? ""] ?? "")".trimmingCharacters(in: .whitespaces)
        }
        sourceTypes = Set((answer["citations"] as? [[String: Any]] ?? []).compactMap { ($0["evidence"] as? [String: Any])?["source_type"] as? String })
        citations = (answer["citations"] as? [[String: Any]] ?? []).enumerated().map { index, citation in
            let evidence = citation["evidence"] as? [String: Any] ?? [:]
            let locator = evidence["locator"] as? [String: Any] ?? [:]
            let kind = c.sourceKinds[evidence["source_type"] as? String ?? ""] ?? ""
            var template = c.locatorKinds[locator["kind"] as? String ?? ""] ?? c.locatorKinds["span_only"] ?? ""
            for (field, value) in locator where field != "kind" { template = template.replacingOccurrences(of: "{\(field)}", with: "\(value)") }
            if template.contains("{") { template = c.locatorKinds["span_only"] ?? "" }
            return CitationView(id: index, label: "\(kind), \(template)", quote: citation["quote"] as? String)
        }
    }
}
