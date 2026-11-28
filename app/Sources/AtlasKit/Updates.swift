import Foundation

/// Updates (UI/UX specification: updates are explained in plain words, never silent, and never touch the owner's data). The owner picks a folder that holds a signed release; the Core checks the signature
/// and the hash before anything is unpacked, installs atomically, and keeps the previous version so the owner can go back.
public struct UpdateView: Equatable {
    public let installedLine: String
    public let canRollBack: Bool
}

public enum UpdateOutcome {
    public static func status(_ response: [String: Any]) -> LoadState<UpdateView> {
        guard let canRollBack = response["can_roll_back"] as? Bool else { return .unavailable(.unknownState) }
        let installed = response["installed"] as? String
        let line = installed.map { "Atlas version \($0). Your data is not changed by updates." } ?? "This copy of Atlas is not installed through the updater."
        return .loaded(UpdateView(installedLine: line, canRollBack: canRollBack))
    }

    /// The plain-words reason an update was refused; every one of them changed nothing.
    public static func refusal(_ code: String) -> String {
        switch code {
        case "bad_signature": return "That update is not signed by Atlas, so it was not installed."
        case "bad_manifest", "bad_version": return "That update's description is damaged, so it was not installed."
        case "bad_artefact", "unsafe_artefact": return "That update's files are damaged or unsafe, so it was not installed."
        case "artefact_does_not_match_manifest": return "That update does not match what was signed, so it was not installed."
        case "not_newer": return "That update is not newer than the version you have."
        case "version_already_on_disk": return "That version is already on this Mac."
        case "unhealthy_rolled_back", "unhealthy_first_install": return "The new version did not start properly, so Atlas went back to the one that works."
        case "nothing_to_roll_back_to": return "There is no earlier version to go back to."
        case "bad_release_folder": return "That folder does not hold a complete update (manifest.json, manifest.sig and artefact.zip)."
        default: return "That update could not be installed. Nothing was changed."
        }
    }

    /// What the owner is told after an install or a rollback: the refusal's reason, or that a restart finishes it.
    public static func result(_ response: [String: Any]) -> (message: String, succeeded: Bool) {
        if let refused = response["refused"] as? String { return (refusal(refused), false) }
        guard let version = response["installed"] as? String else { return ("Atlas cannot say what happened. Nothing was changed.", false) }
        let restart = (response["restart_needed"] as? Bool) == true
        return (restart ? "Atlas \(version) is ready. Quit and reopen Atlas to use it." : "Atlas \(version) is installed.", true)
    }
}
