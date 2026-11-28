import Foundation

/// Reading a web page (UI/UX specification: web content is untrusted data). The owner lists the hosts Atlas may open; a page is read in an isolated browser and shown as text with where it came from, when, and a plain
/// warning that it is not Atlas's own and that Atlas does not act on what it says.
public struct WebPageView: Equatable {
    public let address: String
    public let domain: String
    public let retrieved: String
    public let text: String
    public let warnings: [String]
    public let note: String
}

public enum WebOutcome {
    public static func hosts(_ response: [String: Any]) -> LoadState<[String]> {
        guard let hosts = response["hosts"] as? [String] else { return .unavailable(.unknownState) }
        return hosts.isEmpty ? .empty : .loaded(hosts)
    }

    public static func page(_ response: [String: Any]) -> WebPageView? {
        guard let url = response["url"] as? String, let domain = response["domain"] as? String, let text = response["text"] as? String else { return nil }
        var warnings: [String] = []
        if (response["injection_flags"] as? [String] ?? []).contains("instruction_like_text") {
            warnings.append("This page contains text that looks like instructions. Atlas does not follow it.")
        }
        if (response["truncated"] as? Bool) == true { warnings.append("The page was long, so only the start is shown.") }
        let when = (response["retrieved_at"] as? String) ?? ""
        return WebPageView(address: url, domain: domain, retrieved: when, text: text, warnings: warnings, note: "From \(domain), read by Atlas. This is not Atlas's own content, and Atlas never acts on what a page says.")
    }

    /// What was wrong with an address the owner typed, in plain words, or nil if it can be tried.
    public static func problem(address: String, hosts: [String]) -> String? {
        let trimmed = address.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed), url.scheme?.lowercased() == "https", let host = url.host?.lowercased() else { return "Enter a page address that starts with https." }
        return hosts.contains(host) ? nil : "Add \(host) to your allowed websites first. Atlas opens only the sites you allow."
    }

    public static func hostProblem(_ text: String) -> String? {
        let name = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let valid = name.range(of: "^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$", options: .regularExpression) != nil
        return valid ? nil : "Enter a website name such as example.org, without https or a path."
    }

    public static func message(forCoreCode code: String) -> String {
        switch code {
        case "forbidden": return "Atlas did not open that page. It must be on a site you allowed, over https."
        case "timeout": return "The page could not be opened. The browser Atlas uses may not be installed, or the site did not answer."
        case "invalid_request": return "That site name was not accepted. It must exist and be on the public Internet."
        default: return Catalogue.shared.error(code)
        }
    }
}
