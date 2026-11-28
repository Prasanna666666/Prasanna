import Foundation

/// Plain names and explanations for source types (the policy's names never reach the screen).
public enum SourceNames {
    public static func title(_ type: String) -> String {
        switch type {
        case "documents": return "Documents"
        case "mail": return "Mail"
        case "finance": return "Finance"
        case "health": return "Health"
        case "calendar": return "Calendar"
        case "contacts": return "Contacts"
        case "notes": return "Notes"
        case "photos": return "Photos"
        default: return type.prefix(1).uppercased() + type.dropFirst()
        }
    }

    /// Finance and Health are sensitive domains: turning them on says so plainly.
    public static func isSensitive(_ type: String) -> Bool { type == "finance" || type == "health" }

    public static func explanation(_ type: String) -> String {
        if type == "photos" { return "Atlas reads only the dates, kinds and sizes of your photos on this Mac, never the pictures. macOS will ask you once." }
        return isSensitive(type) ? "Sensitive. Atlas reads it only on this Mac, only while this is on, and never sends it anywhere." : "Atlas reads it only on this Mac, only while this is on."
    }
}

/// The Finance area (UI/UX specification 4.6): spending computed by the Core from the owner's own transactions. It shows only what is computed, says so, and never presents a rounded figure
/// as exact or an estimate as a verified balance.
public struct FinanceView: Equatable {
    public struct Line: Equatable { public let label: String; public let amount: String }

    public let monthTitle: String
    public let total: String
    public let categories: [Line]
    public let changeLine: String?
    public let months: [Line]
    public let basis: String
}

public enum FinanceOutcome {
    private static let monthNames = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]

    /// "2026-10" becomes "October 2026"; anything else is shown as it came (never guessed).
    public static func monthTitle(_ month: String) -> String {
        let parts = month.split(separator: "-")
        guard parts.count == 2, let year = Int(parts[0]), let number = Int(parts[1]), (1...12).contains(number) else { return month }
        return "\(monthNames[number - 1]) \(year)"
    }

    /// Money exactly as the Core sent it, with the currency symbol in front. No arithmetic and no rounding happens here.
    public static func money(_ amount: String, currency: String) -> String {
        let symbol = currency == "EUR" ? "€" : currency + " "
        return amount.hasPrefix("-") ? "-" + symbol + amount.dropFirst() : symbol + amount
    }

    public static func from(_ response: [String: Any]) -> LoadState<FinanceView> {
        let currency = response["currency"] as? String ?? "EUR"
        switch response["state"] as? String ?? "" {
        case "denied": return .denied("Finance is off. Turn it on in Settings and Atlas will show your spending, computed on this Mac.")
        case "empty": return .empty
        case "ready":
            guard let latest = response["latest"] as? [String: Any], let month = latest["month"] as? String, let total = latest["total"] as? String else { return .unavailable(.unknownState) }
            let categories = (latest["categories"] as? [[String: Any]] ?? []).compactMap { entry -> FinanceView.Line? in
                guard let name = entry["category"] as? String, let amount = entry["total"] as? String else { return nil }
                return FinanceView.Line(label: name, amount: money(amount, currency: currency))
            }
            let months = (response["months"] as? [[String: Any]] ?? []).compactMap { entry -> FinanceView.Line? in
                guard let m = entry["month"] as? String, let amount = entry["total"] as? String else { return nil }
                return FinanceView.Line(label: monthTitle(m), amount: money(amount, currency: currency))
            }
            var change: String?
            if let previous = latest["previous_total"] as? String, let delta = latest["delta"] as? String {
                let direction = delta.hasPrefix("-") ? "less" : "more"
                let size = money(delta.hasPrefix("-") ? String(delta.dropFirst()) : delta, currency: currency)
                var line = "\(size) \(direction) than the month before (\(money(previous, currency: currency)))."
                if let percent = latest["percent"] as? String { line += " About \(percent.hasPrefix("-") ? String(percent.dropFirst()) : percent)% (rounded)." }
                change = line
            }
            let count = response["transaction_count"] as? Int ?? 0
            let basis = "Spending only, added up by Atlas from \(count) transactions on this Mac. These are not account balances."
            return .loaded(FinanceView(monthTitle: monthTitle(month), total: money(total, currency: currency), categories: categories, changeLine: change, months: months, basis: basis))
        default: return .unavailable(.unknownState)
        }
    }
}
