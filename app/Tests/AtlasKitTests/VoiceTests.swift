import XCTest
@testable import AtlasKit

final class FakeVoice: VoiceInput {
    var availability: VoiceAvailability = .available
    var access: VoiceAccess = .granted
    var partialHandler: ((String) -> Void)?
    var finishedHandler: ((Result<String, VoiceFailure>) -> Void)?
    var started = 0, stopped = 0

    func requestAccess(_ done: @escaping (VoiceAccess) -> Void) { done(access) }
    func start(partial: @escaping (String) -> Void, finished: @escaping (Result<String, VoiceFailure>) -> Void) { started += 1; partialHandler = partial; finishedHandler = finished }
    func stop() { stopped += 1 }
}

final class VoiceTests: XCTestCase {
    private func session(_ voice: FakeVoice, draft: String = "") -> (VoiceSession, () -> String) {
        var text = draft
        return (VoiceSession(input: voice, draft: { text }, setDraft: { text = $0 }), { text })
    }

    func testSpokenWordsAreAddedAfterWhatWasTypedAndShownAsTheyArrive() {
        let voice = FakeVoice()
        let (s, draft) = session(voice, draft: "What is the rent")
        s.toggle()
        XCTAssertEqual(s.state, .listening(""))
        voice.partialHandler?("in October")
        XCTAssertEqual(draft(), "What is the rent in October")
        XCTAssertEqual(s.state, .listening("in October"))
        voice.finishedHandler?(.success("in October please"))
        XCTAssertEqual(draft(), "What is the rent in October please")
        XCTAssertEqual(s.state, .idle)
    }

    func testAFailureOrSilencePutsTheTypedTextBackExactly() {
        let voice = FakeVoice()
        let (s, draft) = session(voice, draft: "typed text")
        s.toggle()
        voice.partialHandler?("half heard")
        voice.finishedHandler?(.failure(.noSpeech))
        XCTAssertEqual(draft(), "typed text")
        XCTAssertEqual(s.state, .failed(VoiceMessages.noSpeech))
        s.toggle()
        voice.finishedHandler?(.failure(.interrupted))
        XCTAssertEqual(s.state, .failed(VoiceMessages.interrupted))
        XCTAssertEqual(draft(), "typed text")
    }

    func testDeniedPermissionAndMissingOnDeviceSpeechExplainThemselvesAndNeverStartListening() {
        let denied = FakeVoice()
        denied.access = .denied
        let (a, _) = session(denied)
        a.toggle()
        XCTAssertEqual(a.state, .failed(VoiceMessages.denied))
        XCTAssertEqual(denied.started, 0)
        let offDevice = FakeVoice()
        offDevice.availability = .unavailable(VoiceMessages.unavailableOnDevice)
        let (b, _) = session(offDevice)
        b.toggle()
        XCTAssertEqual(b.state, .failed(VoiceMessages.unavailableOnDevice))
        XCTAssertEqual(offDevice.started, 0)  // speech is never sent anywhere to make it work
        XCTAssertFalse(b.availability.isAvailable)
    }

    func testTheStateIsReportedAsItChangesSoTheButtonFollowsAlong() {
        let voice = FakeVoice()
        let (s, _) = session(voice)
        var seen: [VoiceState] = []
        s.onChange = { seen.append($0) }
        s.toggle()
        voice.finishedHandler?(.success("hello"))
        XCTAssertEqual(seen, [.asking, .listening(""), .idle])
    }

    func testTogglingWhileListeningStopsAndMergeNeverReplacesOrDoublesSpaces() {
        let voice = FakeVoice()
        let (s, _) = session(voice)
        s.toggle()
        s.toggle()
        XCTAssertEqual(voice.stopped, 1)
        XCTAssertEqual(VoiceDictation.merge(draft: "  one ", spoken: " two "), "one two")
        XCTAssertEqual(VoiceDictation.merge(draft: "", spoken: "two"), "two")
        XCTAssertEqual(VoiceDictation.merge(draft: "one", spoken: "   "), "one")
    }
}
