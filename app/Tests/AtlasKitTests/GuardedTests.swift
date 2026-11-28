import XCTest
@testable import AtlasKit

/// MAC-20 (review 6098896232): the AppModel runs its answer, Library search and citation fetch through `Guarded.run` with its `ResultGeneration`.
/// These tests hold each request open, change access while it waits, then let it return: a result or an error from before the change is never
/// delivered, re-enabling the source does not let it through, and a retry after the change is delivered.
@MainActor
final class GuardedTests: XCTestCase {
    /// A request the test holds open and later answers.
    final class Held<T> {
        var continuation: CheckedContinuation<T, Error>?
        func wait() async throws -> T { try await withCheckedThrowingContinuation { continuation = $0 } }
    }

    final class Seen<T> {
        var delivered: [T] = []
        var errors = 0
        var stale = 0
    }

    private func start<T>(_ generation: ResultGeneration, _ held: Held<T>, _ seen: Seen<T>) -> Task<Void, Never> {
        Task { @MainActor in
            await Guarded.run(generation, work: { try await held.wait() }, deliver: { seen.delivered.append($0) }, failed: { _ in seen.errors += 1 }, stale: { seen.stale += 1 })
        }
    }

    private func suspended<T>(_ held: Held<T>) async {
        while held.continuation == nil { await Task.yield() }
    }

    func testAnAnswerThatReturnsAfterAWithdrawalIsNotShownEvenIfTheSourceWasTurnedOnAgain() async {
        let generation = ResultGeneration(), held = Held<String>(), seen = Seen<String>()
        let run = start(generation, held, seen)
        await suspended(held)
        generation.advance()  // the owner withdraws a source while the answer is pending ...
        // ... and turns it on again: the scope is the same as before, but the generation only moves forward
        held.continuation?.resume(returning: "answer from before the change")
        await run.value
        XCTAssertEqual(seen.delivered, [])
        XCTAssertEqual(seen.stale, 1)
        XCTAssertEqual(seen.errors, 0)
    }

    func testAnErrorThatReturnsAfterAWithdrawalIsNotShownEither() async {
        let generation = ResultGeneration(), held = Held<String>(), seen = Seen<String>()
        let run = start(generation, held, seen)
        await suspended(held)
        generation.advance()
        held.continuation?.resume(throwing: AtlasError.core(code: "source_denied"))
        await run.value
        XCTAssertEqual(seen.errors, 0)
        XCTAssertEqual(seen.stale, 1)
    }

    func testARetryAfterTheChangeIsDeliveredAndAnUnchangedRequestIsDeliveredAsBefore() async {
        let generation = ResultGeneration()
        let first = Held<String>(), seen = Seen<String>()
        let stale = start(generation, first, seen)
        await suspended(first)
        generation.advance()
        first.continuation?.resume(returning: "old")
        await stale.value
        let retry = Held<String>()
        let fresh = start(generation, retry, seen)  // the retry takes its token after the change
        await suspended(retry)
        retry.continuation?.resume(returning: "new")
        await fresh.value
        XCTAssertEqual(seen.delivered, ["new"])
        XCTAssertEqual(seen.stale, 1)
        let failing = Held<String>()
        let failed = start(generation, failing, seen)
        await suspended(failing)
        failing.continuation?.resume(throwing: AtlasError.core(code: "internal_error"))
        await failed.value
        XCTAssertEqual(seen.errors, 1)  // with no change in between, an error is shown as usual
    }

    func testADelayedCitationPassageIsNotWrittenAfterAWithdrawal() async {
        let generation = ResultGeneration(), held = Held<String>(), seen = Seen<String>()
        let run = start(generation, held, seen)
        await suspended(held)
        generation.advance()  // the withdrawal closed the evidence panel while the passage was being fetched
        held.continuation?.resume(returning: "the cited passage")
        await run.value
        XCTAssertEqual(seen.delivered, [])
        XCTAssertEqual(seen.stale, 1)
    }
}
