import XCTest
@testable import AtlasKit

final class RecordsTests: XCTestCase {
    func testTheCoreListBecomesRowsAndAnEmptyListIsAnEmptyStateNotABlankPanel() {
        let state = RecordsOutcome.from(["records": [["id": "n1", "title": "Passport", "date": "2026-10-18T00:00:00+00:00", "version": 2, "fields": ["text": "Renew it."]]]])
        guard case .loaded(let rows) = state else { return XCTFail("expected rows") }
        XCTAssertEqual(rows.first?.detail(for: .notes), "Renew it.")
        XCTAssertEqual(rows.first?.version, 2)
        XCTAssertNotNil(RecordsOutcome.from(["records": []]).notice)
        guard case .unavailable = RecordsOutcome.from([:]) else { return XCTFail("expected unavailable") }
    }

    func testADraftSaysWhatIsWrongInPlainWordsAndOnlyAValidDraftHasAPayload() {
        var note = RecordDraft(domain: .notes)
        XCTAssertEqual(note.problem(), "Enter a title.")
        note.title = "Passport"
        XCTAssertEqual(note.problem(), "Write the note.")
        XCTAssertNil(note.createPayload(id: "x", now: Date()))
        note.text = "Renew it."
        XCTAssertNil(note.problem())
        let payload = note.createPayload(id: "notes-1", now: Date(timeIntervalSince1970: 0))!
        XCTAssertEqual(payload["id"] as? String, "notes-1")
        XCTAssertEqual((payload["fields"] as? [String: String])?["text"], "Renew it.")

        var event = RecordDraft(domain: .calendar)
        event.title = "Dentist"
        XCTAssertEqual(event.problem(), "Choose when it starts.")
        event.starts = Date(timeIntervalSince1970: 3600)
        event.ends = Date(timeIntervalSince1970: 0)
        XCTAssertEqual(event.problem(), "The end cannot be before the start.")
        event.ends = Date(timeIntervalSince1970: 7200)
        let fields = event.createPayload(id: "calendar-1", now: Date())!["fields"] as? [String: String]
        XCTAssertEqual(fields?["starts"], "1970-01-01T01:00:00Z")
        XCTAssertEqual(fields?["ends"], "1970-01-01T02:00:00Z")
        XCTAssertNil(fields?["location"])  // an empty optional field is not sent

        var person = RecordDraft(domain: .contacts)
        XCTAssertEqual(person.problem(), "Enter a name.")
        person.title = "Jansen"
        person.phone = "0612345678"
        XCTAssertEqual((person.createPayload(id: "contacts-1", now: Date())!["fields"] as? [String: String])?["phone"], "0612345678")
    }

    func testIdsAreAcceptedByTheCoreAndTheAreasKnowTheirActions() {
        let id = RecordIdentity.make(domain: .notes)
        XCTAssertTrue(id.hasPrefix("notes-"))
        XCTAssertNotNil(id.range(of: "^[A-Za-z0-9._-]{1,120}$", options: .regularExpression))
        for domain in OwnDomain.allCases {
            XCTAssertEqual(domain.createAction, domain.rawValue + ".create")
            XCTAssertEqual(OwnDomain(areaTitle: domain.title), domain)
            XCTAssertFalse(domain.emptyText.isEmpty)
            XCTAssertFalse(domain.symbol.isEmpty)
        }
        XCTAssertNil(OwnDomain(areaTitle: "Finance"))
    }
}
