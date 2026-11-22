import Foundation

/// Every user-facing sentence, loaded from the same JSON the Python reference client and its completeness test use.
public struct Catalogue: Decodable {
    public let taskStates: [String: String]
    public let progressSteps: [String: String]
    public let errors: [String: String]
    public let verification: [String: String]
    public let limitations: [String: String]
    public let coverageState: [String: String]
    public let notSearchedReasons: [String: String]
    public let modelRoles: [String: String]
    public let modelLine: String
    public let modelLineUnknown: String
    public let coverageLine: String
    public let coverageLineUnknownTotal: String
    public let noCitations: String
    public let locatorKinds: [String: String]
    public let sourceKinds: [String: String]
    public let actions: [String: String]

    enum CodingKeys: String, CodingKey {
        case taskStates = "task_states", progressSteps = "progress_steps", errors, verification, limitations
        case coverageState = "coverage_state", notSearchedReasons = "not_searched_reasons", modelRoles = "model_roles"
        case modelLine = "model_line", modelLineUnknown = "model_line_unknown", coverageLine = "coverage_line"
        case coverageLineUnknownTotal = "coverage_line_unknown_total", noCitations = "no_citations"
        case locatorKinds = "locator_kinds", sourceKinds = "source_kinds", actions
    }

    public static let shared: Catalogue = {
        guard let url = Bundle.module.url(forResource: "ux_catalogue", withExtension: "json"), let data = try? Data(contentsOf: url),
              let value = try? JSONDecoder().decode(Catalogue.self, from: data) else { fatalError("ux_catalogue.json is missing or malformed") }
        return value
    }()

    public func error(_ code: String) -> String { errors[code] ?? errors["internal_error"] ?? "Something went wrong." }
}

public enum AtlasError: Error {
    case local(String)
    case core(code: String)
    public var message: String {
        switch self {
        case .local: return "Atlas is not running or cannot be reached. Open Atlas and try again."
        case .core(let code): return Catalogue.shared.error(code)
        }
    }
}
