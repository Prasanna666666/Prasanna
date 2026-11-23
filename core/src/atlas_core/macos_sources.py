"""The owner's own Calendar, Contacts, Notes and Photos on macOS, as read-only sources behind the same seam as Mail (Stage 5; G-021 does not apply: these are ordinary sources).

Everything the Core knows about the operating system is behind `Platform`: its permission status for a domain, a request for that permission, and a bounded read of the data as `Record`s. `ObjcPlatform`
is the real one (EventKit, Contacts and Photos through pyobjc; Notes through the system's own scripting interface); tests and Linux use a fake. A source reads nothing unless the platform says the permission is
granted, a denied or undecided permission is reported as such and never guessed, and what is read is metadata and text the owner wrote: Photos gives dates, kind and size, never pixels or locations.

The permission prompt is asked for ONLY when the owner turns the source on (`request`), never while the Core merely checks status.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .access import GRANTED, MISSING, UNKNOWN, PermissionEvidence
from .mail import InMemoryMailbox
from .records import Record, as_message

DOMAINS = ("calendar", "contacts", "notes", "photos")
MAX_RECORDS = 5000
EVENT_WINDOW = (timedelta(days=90), timedelta(days=365))  # how far back and forward calendar events are read
OSASCRIPT_TIMEOUT = 60
NOTES_PROBE_TIMEOUT = 20
PHOTOS_VIDEO = 2  # PHAssetMediaTypeVideo


class Platform(Protocol):
    def status(self, domain: str) -> str:
        """granted | missing | unknown, from the operating system, asking nothing of the owner."""
        ...

    def request(self, domain: str) -> None:
        """Ask the operating system for the permission (shows its prompt once, when it has not been decided)."""
        ...

    def fetch(self, domain: str, now: datetime) -> list[Record]:
        """The domain's records, bounded. Raises PermissionError if the permission is not granted."""
        ...


class MacPermissions:
    """The platform-permission provider for these four domains; anything else goes to `inner`."""

    def __init__(self, platform: Platform, inner: Any, clock: Callable[[], datetime] | None = None) -> None:
        self._platform, self._inner = platform, inner
        self._clock = clock or (lambda: datetime.now(UTC))

    def current(self, source_type: str) -> PermissionEvidence:
        if source_type not in DOMAINS:
            return self._inner.current(source_type)
        try:
            state = self._platform.status(source_type)
        except Exception:  # noqa: BLE001  (no answer is no evidence)
            state = UNKNOWN
        return PermissionEvidence(source_type, state if state in (GRANTED, MISSING) else UNKNOWN, self._clock())


class NativeRecords(InMemoryMailbox):
    """One domain's records from the platform, behind the Mail seam (`list_page`, `read`). The data is read at the first page of a scan, so an index run sees one consistent snapshot; a denied permission
    gives an empty source, never a partial or guessed one."""

    def __init__(self, platform: Platform, domain: str, clock: Callable[[], datetime] | None = None) -> None:
        super().__init__([], order="newest_first")
        self._platform, self.domain = platform, domain
        self._clock = clock or (lambda: datetime.now(UTC))

    def _refresh(self) -> None:
        try:
            records = self._platform.fetch(self.domain, self._clock())
        except (PermissionError, OSError):  # denied, or the system did not answer: an empty source, never a crash or a partial read
            records = []
        self.messages = {}
        for record in records[:MAX_RECORDS]:
            self.messages[record.record_id] = as_message(record)

    def list_page(self, cursor: str | None, limit: int) -> Any:
        if cursor is None:
            self._refresh()
        return super().list_page(cursor, limit)


# -- the real platform -----------------------------------------------------------------------------------------------------------------------------
_AUTH = {  # EventKit, Contacts and Photos authorization statuses, as the system defines them
    "full": (3, 4),  # authorized / full access; Photos also 4 = limited (the library the owner chose)
    "undecided": (0,),
}


def _iso(value: Any) -> str:
    """An NSDate as an ISO 8601 UTC instant."""
    return datetime.fromtimestamp(float(value.timeIntervalSince1970()), UTC).isoformat()


def _clean(text: Any, limit: int = 4000) -> str:
    return " ".join(str(text or "").split())[:limit]


class ObjcPlatform:
    """The real platform. Importing its frameworks fails off macOS, so it is constructed only there; every read goes through the system's own permission, which this process cannot widen."""

    def __init__(self, runner: Callable[..., Any] = subprocess.run) -> None:
        import Contacts
        import EventKit
        import Photos

        self._ek, self._cn, self._ph, self._run = EventKit, Contacts, Photos, runner
        self._notes_probe: tuple[datetime, str] | None = None

    # permission ------------------------------------------------------------------------------------------------------------------------------------
    def _map(self, code: int, undecided: int = 0) -> str:
        if code in _AUTH["full"]:
            return GRANTED
        return UNKNOWN if code == undecided else MISSING

    def status(self, domain: str) -> str:
        if domain == "calendar":
            return self._map(int(self._ek.EKEventStore.authorizationStatusForEntityType_(self._ek.EKEntityTypeEvent)))
        if domain == "contacts":
            return self._map(int(self._cn.CNContactStore.authorizationStatusForEntityType_(self._cn.CNEntityTypeContacts)))
        if domain == "photos":
            return self._map(int(self._ph.PHPhotoLibrary.authorizationStatusForAccessLevel_(self._ph.PHAccessLevelReadWrite)))
        if domain == "notes":
            return self._notes_status()
        return UNKNOWN

    def request(self, domain: str) -> None:
        def ignore(*_args: Any) -> None:
            return None

        if domain == "calendar":
            self._ek.EKEventStore.alloc().init().requestFullAccessToEventsWithCompletion_(ignore)
        elif domain == "contacts":
            self._cn.CNContactStore.alloc().init().requestAccessForEntityType_completionHandler_(self._cn.CNEntityTypeContacts, ignore)
        elif domain == "photos":
            self._ph.PHPhotoLibrary.requestAuthorizationForAccessLevel_handler_(self._ph.PHAccessLevelReadWrite, ignore)
        elif domain == "notes":
            self._script("Application('Notes').name()")  # the first scripted call shows the system's Automation prompt

    # notes (no framework exists: the system's scripting interface, under the Automation permission) -----------------------------------------------
    def _script(self, source: str, timeout: float = OSASCRIPT_TIMEOUT) -> str:
        try:
            done = self._run(["osascript", "-l", "JavaScript", "-e", source], capture_output=True, text=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise OSError("notes_timeout") from None  # Notes did not answer in time (it may be starting, or waiting on a prompt): no data, never a hang
        if done.returncode != 0:
            raise PermissionError("notes_not_permitted") if "-1743" in (done.stderr or "") else OSError("notes_failed")
        return str(done.stdout)

    def _notes_status(self) -> str:
        now = datetime.now(UTC)
        if self._notes_probe is not None and now - self._notes_probe[0] < timedelta(minutes=5):
            return self._notes_probe[1]  # a probe can launch the Notes app: asked at most every few minutes
        try:
            self._script("Application('Notes').name()", NOTES_PROBE_TIMEOUT)
            state = GRANTED
        except PermissionError:
            state = MISSING
        except OSError:
            state = UNKNOWN
        self._notes_probe = (now, state)
        return state

    # reading ---------------------------------------------------------------------------------------------------------------------------------------
    def fetch(self, domain: str, now: datetime) -> list[Record]:
        if self.status(domain) != GRANTED:
            raise PermissionError(domain)
        return {"calendar": self._events, "contacts": self._contacts, "notes": self._notes, "photos": self._photos}[domain](now)

    def _events(self, now: datetime) -> list[Record]:
        from Foundation import NSDate

        store = self._ek.EKEventStore.alloc().init()
        start, end = (now - EVENT_WINDOW[0]).timestamp(), (now + EVENT_WINDOW[1]).timestamp()
        predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
            NSDate.dateWithTimeIntervalSince1970_(start), NSDate.dateWithTimeIntervalSince1970_(end), None
        )
        out = []
        for event in list(store.eventsMatchingPredicate_(predicate) or [])[:MAX_RECORDS]:
            starts = _iso(event.startDate())
            fields = {"starts": starts, "ends": _iso(event.endDate())}
            if event.location():
                fields["location"] = _clean(event.location(), 300)
            names = [_clean(p.name(), 80) for p in (event.attendees() or []) if p.name()]
            if names:
                fields["attendees"] = ", ".join(names)[:500]
            if event.notes():
                fields["note"] = _clean(event.notes())
            out.append(
                Record(
                    f"cal-{_clean(event.eventIdentifier(), 100)}".replace("/", "_").replace(":", "_"),
                    "calendar",
                    starts,
                    _clean(event.title(), 200) or "Event",
                    fields,
                )
            )
        return out

    def _contacts(self, now: datetime) -> list[Record]:
        cn = self._cn
        keys = [
            cn.CNContactGivenNameKey,
            cn.CNContactFamilyNameKey,
            cn.CNContactOrganizationNameKey,
            cn.CNContactJobTitleKey,
            cn.CNContactEmailAddressesKey,
            cn.CNContactPhoneNumbersKey,
        ]
        request = cn.CNContactFetchRequest.alloc().initWithKeysToFetch_(keys)
        collected: list[Any] = []
        cn.CNContactStore.alloc().init().enumerateContactsWithFetchRequest_error_usingBlock_(request, None, lambda contact, _stop: collected.append(contact))
        out = []
        for contact in collected[:MAX_RECORDS]:
            name = _clean(f"{contact.givenName()} {contact.familyName()}", 200)
            if not name:
                continue
            fields = {"name": name}
            if contact.organizationName():
                fields["organisation"] = _clean(contact.organizationName(), 200)
            if contact.jobTitle():
                fields["role"] = _clean(contact.jobTitle(), 200)
            emails = [_clean(v.value(), 200) for v in (contact.emailAddresses() or [])]
            phones = [_clean(v.value().stringValue(), 60) for v in (contact.phoneNumbers() or [])]
            if emails:
                fields["email"] = ", ".join(emails)[:400]
            if phones:
                fields["phone"] = ", ".join(phones)[:200]
            out.append(Record(f"con-{_clean(contact.identifier(), 100)}".replace("/", "_").replace(":", "_"), "contacts", now.isoformat(), name, fields))
        return out

    def _notes(self, now: datetime) -> list[Record]:
        script = (
            "JSON.stringify(Application('Notes').notes().slice(0,"
            + str(MAX_RECORDS)
            + ").map(n=>({id:n.id(),name:n.name(),text:n.plaintext(),modified:n.modificationDate().toISOString()})))"
        )
        out = []
        for row in json.loads(self._script(script) or "[]"):
            text = _clean(row.get("text"), 20000)
            if text:
                ident = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(row.get("id", "")))[-100:]
                out.append(Record(f"note-{ident}", "notes", str(row.get("modified", now.isoformat())), _clean(row.get("name"), 200) or "Note", {"text": text}))
        return out

    def _photos(self, now: datetime) -> list[Record]:
        ph = self._ph
        options = ph.PHFetchOptions.alloc().init()
        options.setFetchLimit_(MAX_RECORDS)
        assets = ph.PHAsset.fetchAssetsWithOptions_(options)
        out = []
        for index in range(min(int(assets.count()), MAX_RECORDS)):
            asset = assets.objectAtIndex_(index)
            if asset.creationDate() is None:
                continue
            taken = _iso(asset.creationDate())
            kind = "video" if int(asset.mediaType()) == PHOTOS_VIDEO else "photo"
            ident = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in str(asset.localIdentifier()))[:100]
            fields = {"kind": kind, "taken": taken, "size": f"{int(asset.pixelWidth())}x{int(asset.pixelHeight())}"}
            if asset.isFavorite():
                fields["favourite"] = "yes"
            out.append(Record(f"pho-{ident}", "photos", taken, f"{kind.capitalize()} {taken[:10]}", fields))
        return out
