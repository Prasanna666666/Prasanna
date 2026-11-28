import AtlasKit
import AVFoundation
import Foundation
import Speech

/// The real voice input: the system's speech recognizer in its ON-DEVICE mode only (`requiresOnDeviceRecognition`), fed by the microphone. If the system has no on-device model for the owner's language,
/// `availability` says so and the app shows no microphone button; this class never falls back to server recognition.
final class SystemSpeech: VoiceInput {
    private let recognizer = SFSpeechRecognizer(locale: Locale.current)
    private let engine = AVAudioEngine()
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?

    var availability: VoiceAvailability {
        guard let recognizer, recognizer.isAvailable, recognizer.supportsOnDeviceRecognition else { return .unavailable(VoiceMessages.unavailableOnDevice) }
        return .available
    }

    func requestAccess(_ done: @escaping (VoiceAccess) -> Void) {
        SFSpeechRecognizer.requestAuthorization { speech in
            guard speech == .authorized else { DispatchQueue.main.async { done(speech == .restricted ? .restricted : .denied) }; return }
            AVCaptureDevice.requestAccess(for: .audio) { allowed in DispatchQueue.main.async { done(allowed ? .granted : .denied) } }
        }
    }

    func start(partial: @escaping (String) -> Void, finished: @escaping (Result<String, VoiceFailure>) -> Void) {
        guard let recognizer, recognizer.supportsOnDeviceRecognition else { finished(.failure(.unavailable)); return }
        let request = SFSpeechAudioBufferRecognitionRequest()
        request.requiresOnDeviceRecognition = true  // never a server
        request.shouldReportPartialResults = true
        self.request = request
        let input = engine.inputNode
        input.removeTap(onBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: input.outputFormat(forBus: 0)) { buffer, _ in request.append(buffer) }
        do { engine.prepare(); try engine.start() } catch { finished(.failure(.interrupted)); return }
        task = recognizer.recognitionTask(with: request) { [weak self] result, error in
            DispatchQueue.main.async {
                if let result {
                    let text = result.bestTranscription.formattedString
                    if result.isFinal { self?.teardown(); finished(text.isEmpty ? .failure(.noSpeech) : .success(text)) } else { partial(text) }
                } else if error != nil {
                    self?.teardown()
                    finished(.failure(.interrupted))
                }
            }
        }
    }

    func stop() {
        engine.stop()
        request?.endAudio()  // the recognizer then delivers its final transcript
    }

    private func teardown() {
        engine.stop()
        engine.inputNode.removeTap(onBus: 0)
        request = nil
        task = nil
    }
}
