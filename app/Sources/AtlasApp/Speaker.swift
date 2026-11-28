import AtlasKit
import AVFoundation
import Foundation

/// The Mac's own speech synthesizer: voices installed on this Mac, no network.
final class SystemSpeaker: NSObject, Speaker, AVSpeechSynthesizerDelegate {
    private let synthesizer = AVSpeechSynthesizer()
    private var done: (() -> Void)?

    override init() { super.init(); synthesizer.delegate = self }

    var isSpeaking: Bool { synthesizer.isSpeaking }

    func speak(_ text: String, finished: @escaping () -> Void) {
        done = finished
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = AVSpeechSynthesisVoice(language: Locale.current.identifier.replacingOccurrences(of: "_", with: "-"))
        synthesizer.speak(utterance)
    }

    func stop() { synthesizer.stopSpeaking(at: .immediate); done = nil }

    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didFinish utterance: AVSpeechUtterance) { DispatchQueue.main.async { self.done?(); self.done = nil } }
    func speechSynthesizer(_ synthesizer: AVSpeechSynthesizer, didCancel utterance: AVSpeechUtterance) { DispatchQueue.main.async { self.done?(); self.done = nil } }
}
