import Foundation

/// Voice input (dictation into the composer). Local only: speech is turned into text on this Mac, by the system's on-device recognizer, and nothing is sent to a server. If the system cannot do that
/// for the owner's language, voice is unavailable and the microphone button is not shown; a person is never offered a button that would send speech anywhere.
public enum VoiceAvailability: Equatable {
    case available
    case unavailable(String)

    public var isAvailable: Bool { self == .available }
}

public enum VoiceAccess: Equatable { case granted, denied, restricted }

/// The platform seam. The app's `SystemSpeech` is the real one (on-device speech recognition and the microphone); tests use a fake.
public protocol VoiceInput: AnyObject {
    var availability: VoiceAvailability { get }
    func requestAccess(_ done: @escaping (VoiceAccess) -> Void)
    /// Starts listening. `partial` receives the whole transcript so far, `finished` the final transcript or a failure.
    func start(partial: @escaping (String) -> Void, finished: @escaping (Result<String, VoiceFailure>) -> Void)
    func stop()
}

public enum VoiceFailure: Error, Equatable { case noSpeech, interrupted, unavailable }

public enum VoiceState: Equatable {
    case idle
    case asking
    case listening(String)
    case failed(String)

    public var isListening: Bool {
        if case .listening = self { return true }
        return false
    }
}

public enum VoiceMessages {
    public static let unavailableOnDevice = "Voice needs this Mac to understand speech on its own, and it cannot do that for your language. Nothing is sent anywhere, so voice is off."
    public static let denied = "Atlas cannot use the microphone or speech recognition. You can allow it in System Settings, Privacy and Security."
    public static let noSpeech = "Atlas did not hear anything. Try again."
    public static let interrupted = "Listening stopped. Try again."
}

/// What dictation does to the text the owner already typed: the spoken words are added after it, with one space, never replacing it, so nothing typed is lost.
public enum VoiceDictation {
    public static func merge(draft: String, spoken: String) -> String {
        let said = spoken.trimmingCharacters(in: .whitespacesAndNewlines)
        if said.isEmpty { return draft }
        let typed = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        return typed.isEmpty ? said : typed + " " + said
    }
}

/// The dictation session the composer drives. It owns the state; the platform does the listening. The draft is only changed by `commit`, so abandoning a dictation leaves the question exactly as it was.
public final class VoiceSession {
    public private(set) var state: VoiceState = .idle { didSet { if state != oldValue { onChange?(state) } } }
    /// Called whenever the state changes, so a screen can follow along.
    public var onChange: ((VoiceState) -> Void)?
    private let input: VoiceInput
    private let baseDraft: () -> String
    private let setDraft: (String) -> Void
    private var original = ""

    public init(input: VoiceInput, draft: @escaping () -> String, setDraft: @escaping (String) -> Void) {
        self.input = input; self.baseDraft = draft; self.setDraft = setDraft
    }

    public var availability: VoiceAvailability { input.availability }

    /// Asks for the permissions the first time, then listens. Each partial transcript is shown in the composer; the original text is kept to put back if listening fails.
    public func toggle() {
        if state.isListening { stop(); return }
        guard input.availability.isAvailable else {
            state = .failed(VoiceMessages.unavailableOnDevice)
            return
        }
        state = .asking
        input.requestAccess { [weak self] access in
            guard let self else { return }
            guard access == .granted else { self.state = .failed(VoiceMessages.denied); return }
            self.original = self.baseDraft()
            self.state = .listening("")
            self.input.start(
                partial: { [weak self] text in
                    guard let self, self.state.isListening else { return }
                    self.state = .listening(text)
                    self.setDraft(VoiceDictation.merge(draft: self.original, spoken: text))
                },
                finished: { [weak self] result in self?.finish(result) }
            )
        }
    }

    public func stop() { input.stop() }

    private func finish(_ result: Result<String, VoiceFailure>) {
        switch result {
        case .success(let text):
            setDraft(VoiceDictation.merge(draft: original, spoken: text))
            state = .idle
        case .failure(let failure):
            setDraft(original)  // nothing the owner typed is lost, and nothing half-heard is left behind
            switch failure {
            case .noSpeech: state = .failed(VoiceMessages.noSpeech)
            case .interrupted: state = .failed(VoiceMessages.interrupted)
            case .unavailable: state = .failed(VoiceMessages.unavailableOnDevice)
            }
        }
    }
}
