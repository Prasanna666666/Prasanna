import Foundation

/// Reading an answer aloud. Local only: the Mac's own voices speak it, nothing is sent anywhere. What is read is the answer and how far to trust it, in plain order; the citations stay on screen.
public enum AloudText {
    public static func from(_ answer: AnswerView) -> String {
        [answer.text, answer.trust].map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }.joined(separator: " ")
    }
}

public protocol Speaker: AnyObject {
    var isSpeaking: Bool { get }
    func speak(_ text: String, finished: @escaping () -> Void)
    func stop()
}

public enum AloudState: Equatable { case idle, speaking }

/// What the "Read aloud" control does: one answer at a time, press again to stop, and nothing is read for an empty answer.
public final class AloudSession {
    public private(set) var state: AloudState = .idle { didSet { if state != oldValue { onChange?(state) } } }
    public var onChange: ((AloudState) -> Void)?
    private let speaker: Speaker

    public init(speaker: Speaker) { self.speaker = speaker }

    public func toggle(_ text: String) {
        if state == .speaking { speaker.stop(); state = .idle; return }
        let said = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !said.isEmpty else { return }
        state = .speaking
        speaker.speak(said) { [weak self] in self?.state = .idle }
    }
}
