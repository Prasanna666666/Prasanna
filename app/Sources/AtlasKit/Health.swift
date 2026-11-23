import Foundation

/// The Health area (UI/UX specification 4.6): readings summarised by the Core from the owner's own Health records. It shows what was computed, says whether each reading was measured or estimated,
/// labels the average as rounded, and gives no advice or diagnosis.
public struct HealthView: Equatable {
    public struct Measure: Equatable {
        public let title: String
        public let latestLine: String
        public let rangeLine: String
        public let averageLine: String
        public let basisLine: String
    }

    public let measures: [Measure]
    public let basis: String
}

public enum HealthOutcome {
    private static func basisWord(_ basis: String) -> String {
        switch basis {
        case "measured": return "measured"
        case "estimated": return "estimated"
        default: return "not labelled"
        }
    }

    public static func from(_ response: [String: Any]) -> LoadState<HealthView> {
        switch response["state"] as? String ?? "" {
        case "denied": return .denied("Health is off. Turn it on in Settings and Atlas will show your readings, summarised on this Mac.")
        case "empty": return .empty
        case "ready":
            let rows = response["measures"] as? [[String: Any]] ?? []
            let measures = rows.compactMap { row -> HealthView.Measure? in
                guard let name = row["measure"] as? String, let unit = row["unit"] as? String, let count = row["count"] as? Int,
                      let latest = row["latest"] as? [String: Any], let date = latest["date"] as? String, let value = latest["value"] as? String,
                      let minimum = row["minimum"] as? String, let maximum = row["maximum"] as? String, let average = row["average"] as? String else { return nil }
                let basis = basisWord(latest["basis"] as? String ?? "")
                let bases = row["bases"] as? [String: Any] ?? [:]
                let parts = ["measured", "estimated", "unlabelled"].compactMap { key -> String? in
                    let n = bases[key] as? Int ?? 0
                    return n > 0 ? "\(n) \(key == "unlabelled" ? "not labelled" : key)" : nil
                }
                return HealthView.Measure(
                    title: name.prefix(1).uppercased() + name.dropFirst(),
                    latestLine: "Latest: \(value) \(unit) on \(date) (\(basis)).",
                    rangeLine: "Lowest \(minimum) \(unit), highest \(maximum) \(unit), from \(count) \(count == 1 ? "reading" : "readings").",
                    averageLine: "Average \(average) \(unit) (rounded).",
                    basisLine: parts.joined(separator: ", ")
                )
            }
            if measures.isEmpty { return .unavailable(.unknownState) }
            return .loaded(HealthView(measures: measures, basis: "Added up by Atlas on this Mac from your own readings. Units are never converted. This is not medical advice."))
        default: return .unavailable(.unknownState)
        }
    }
}
