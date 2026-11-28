import XCTest
@testable import AtlasKit

final class FakeSpeaker: Speaker {
    var isSpeaking = false
    var spoken: [String] = []
    var stopped = 0
    var finish: (() -> Void)?
    func speak(_ text: String, finished: @escaping () -> Void) { isSpeaking = true; spoken.append(text); finish = finished }
    func stop() { isSpeaking = false; stopped += 1 }
}

final class AloudTests: XCTestCase {
    func testTheAnswerAndHowFarToTrustItAreReadInOrderAndNothingElse() {
        let answer = AnswerView(["answer": "The rent was 412.30 EUR.", "verification": ["status": "verified"]])
        let text = AloudText.from(answer)
        XCTAssertTrue(text.hasPrefix("The rent was 412.30 EUR."))
        XCTAssertGreaterThan(text.count, "The rent was 412.30 EUR.".count)  // the trust line follows
        XCTAssertEqual(AloudText.from(AnswerView(["answer": "  ", "verification": ["status": "nonsense"]])), "")
    }

    func testOneAnswerAtATimeAndPressingAgainStopsAndEmptyTextIsNeverRead() {
        let speaker = FakeSpeaker()
        let session = AloudSession(speaker: speaker)
        var seen: [AloudState] = []
        session.onChange = { seen.append($0) }
        session.toggle("   ")
        XCTAssertTrue(speaker.spoken.isEmpty)
        session.toggle("Hello there.")
        XCTAssertEqual(speaker.spoken, ["Hello there."])
        XCTAssertEqual(session.state, .speaking)
        session.toggle("Hello there.")
        XCTAssertEqual(speaker.stopped, 1)
        XCTAssertEqual(session.state, .idle)
        session.toggle("Again.")
        speaker.finish?()
        XCTAssertEqual(session.state, .idle)
        XCTAssertEqual(seen, [.speaking, .idle, .speaking, .idle])
    }
}
