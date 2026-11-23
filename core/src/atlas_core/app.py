"""The composition root: the one place that builds a running Core from its parts and connects them (WP3 hardening).

It adds no behaviour of its own. It wires what the other modules already guarantee: the owner's designation gates every index and the policy; a revocation purges the index AND
everything the task store derived from it; the model is reached only through the gateway behind the policy gate; coverage comes from the indexes; the API is served on the owner-only
socket. Everything platform-specific is injected (the secure-storage anchor, the OS-permission provider, the real mailbox adapter, the MLX runtime, the Keychain-backed keys), so
this file is verified on Linux with the deterministic fakes and the Mac pieces plug into the same seams.
"""

from __future__ import annotations

import fcntl
import os
import shutil
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .access import OSPermissionProvider, SourceAccess
from .actions import ActionGateway, AuditFile
from .api import CoreApi
from .backup import drill_passed
from .connectors import Adapter, ConnectorHub, SecretStore
from .consent import ConsentService
from .designation import DesignationStore, RollbackAnchor
from .devices import CoreIdentity, DeviceDirectory
from .documents import DocumentIndex
from .egress import EgressGateway
from .events import SafeLog
from .evidence import StoredSource
from .finance_calc import MONEY_DOMAIN
from .health_calc import HEALTH_DOMAIN
from .identity import BootstrapGate, ClientRegistry
from .intelligence import Gateway, ModelRuntime, Router, Signals
from .mail import Mailbox, MailIndex
from .models import Manifest, ModelStore
from .operations import DeviceOperations, Operations
from .policy import PolicyEngine
from .record_actions import register_record_actions
from .records import Record
from .recordstore import RecordStore, StoreError
from .rules import load_rules
from .service import Deps, ResearchGate, TaskService
from .storage import pressure_of
from .sync import SyncService
from .tasks import TaskStore
from .transport import UnixServer, serve_unix
from .updater import UpdateOperations
from .web import EngineFactory, WebReader

INDEX_SLICE = 20
RESCAN_SECONDS = 300  # how often a permitted source is listed again to notice changes


@dataclass
class CoreConfig:
    """Everything that varies by machine. Keys are separate per store (a database key is never shared)."""

    data_dir: Path
    socket_path: Path
    task_key: str
    designation_key: str
    documents_key: str
    mail_key: str
    anchor: RollbackAnchor
    os_permissions: OSPermissionProvider
    manifest: Manifest
    model_record_key: bytes
    runtime: ModelRuntime
    bootstrap_code: str | None = (
        None  # the single-use first-run code, known only to the process that starts the Core; required while no owner client is enrolled
    )
    open_bootstrap: bool = False  # DEVELOPMENT ONLY: accept the first owner with no code (what the first version did); never set it in a real run
    clients: ClientRegistry | None = None  # None: a durable registry in the data folder (the normal case); tests inject one
    documents: tuple[str, Path] | None = None  # (source type name from the policy rules, folder)
    mailbox: tuple[str, Mailbox] | None = None  # (source type name, adapter)
    records: Mapping[str, tuple[Mailbox, str]] = field(
        default_factory=dict
    )  # Stage 5 domains: source type -> (read-only record source, that store's own key); one encrypted index per type
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    allowed_uids: Iterable[int] | None = None
    egress: EgressGateway | None = None  # public-web research; None (the default) means the Core makes no outbound request at all
    edits_key: str | None = None  # the key of the owner's own edits store (Calendar, Contacts, Notes); None means the Core has no owner actions and no sync
    outbox: Callable[[dict[str, Any]], dict[str, Any]] | None = (
        None  # the platform sender for `calendar.send_invitation` (a real adapter is not built; None means the action does not exist)
    )
    erase: Callable[[str], None] | None = None  # the platform's irreversible removal behind the approval-gated `*.erase` actions (None: they do not exist)
    disk_usage: Callable[[Path], tuple[int, int, int]] = shutil.disk_usage  # (total, used, free) of the data folder's disk; tests inject a nearly full one
    web_engine: EngineFactory | None = None  # makes an isolated browser for one allowed host; without it no web reading is offered
    secrets: SecretStore | None = None  # where connector credentials live (the Keychain on the Mac); without it no connectors are offered
    connector_adapters: Mapping[str, Adapter] | None = None  # vendor adapters that replace the bundled one, by integration id
    os_requester: Callable[[str], None] | None = None  # asks the operating system for a source's permission when the owner turns it on
    updates: UpdateOperations | None = None  # the app's own install, when the Core manages one (the update screen is hidden without it)
    closers: tuple[Callable[[], None], ...] = ()  # what the host opened for the Core (its own stores): closed with the Core
    require_restore_drill: bool = False  # when True, Finance and Health cannot be designated until a restore drill has passed in the last 90 days (G-O05: restore is verified before sensitive-domain indexing)
    live_network: bool = False  # the explicit live-network gate: even with a gateway configured, no public search is made unless this is True (off by default)
    log: SafeLog = field(default_factory=SafeLog)


class CoreAlreadyRunning(RuntimeError):
    """Another Core already owns this data folder (its stores, its socket). The second one must not start, bind, or unlink anything."""


def _lock_data_dir(data_dir: Path) -> int:
    fd = os.open(data_dir / "core.lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # released by the OS if the holder dies, so a crash never leaves a stale lock
    except OSError:
        os.close(fd)
        raise CoreAlreadyRunning("another Core owns this data folder") from None
    return fd


class _Retriever:
    def __init__(self, indexes: dict[str, Any]) -> None:
        self._indexes = indexes

    def search(self, source_type: str, query: str) -> Iterable[dict[str, Any]]:
        index = self._indexes.get(source_type)
        return [] if index is None else index.search(source_type, query)


class _Sources:
    """The evidence store: a source id belongs to exactly one index, and an index resolves only its own."""

    def __init__(self, indexes: dict[str, Any]) -> None:
        self._indexes = indexes

    def get(self, source_id: str) -> StoredSource | None:
        for index in self._indexes.values():
            found = index.get(source_id)
            if found is not None:
                return found
        return None


class _Mode:
    """The owner's selected model mode, in memory only: it starts as `default` every time the Core starts (the deep tier is never on by accident)."""

    def __init__(self) -> None:
        self._mode, self._lock = "default", threading.Lock()

    def get(self) -> str:
        with self._lock:
            return self._mode

    def set(self, mode: str) -> None:
        with self._lock:
            self._mode = mode


class Core:
    def __init__(self, config: CoreConfig) -> None:
        c = config
        c.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock_fd = _lock_data_dir(c.data_dir)  # one Core per data folder: taken before any store is opened, held until close() or the process ends
        try:
            self._build(c)
        except BaseException:
            self._release_lock()
            raise

    def _build_indexes(self, c: CoreConfig) -> dict[str, Any]:
        """One encrypted, guarded index per configured source type: documents, Mail, and the Stage 5 domains (the same exact, purgeable index as Mail, one store and one key per type)."""
        indexes: dict[str, Any] = {}
        if c.documents is not None:
            name, root = c.documents
            indexes[name] = DocumentIndex(c.data_dir / "documents.db", c.documents_key, root, name, access=self.access)
        if c.mailbox is not None:
            name, adapter = c.mailbox
            indexes[name] = MailIndex(c.data_dir / "mail.db", c.mail_key, adapter, name, access=self.access)
        for name, (source, key) in c.records.items():
            indexes[name] = MailIndex(c.data_dir / f"{name}.db", key, source, name, access=self.access)
        return indexes

    def _build(self, c: CoreConfig) -> None:
        self.mode = _Mode()
        self.egress = c.egress
        self.config, self.clock = c, c.clock
        self.designation = DesignationStore(c.data_dir / "designation.db", c.designation_key, c.clock, anchor=c.anchor)
        self.designation.verify()
        self.access = SourceAccess(self.designation, c.os_permissions, c.clock)
        self.indexes = self._build_indexes(c)
        self._refresh_adapter_types()
        self.tasks = TaskStore(c.data_dir / "tasks.db", c.task_key)
        models = ModelStore(c.data_dir / "models", c.manifest, c.model_record_key)
        self.gateway = Gateway(models, Router(c.manifest.entries()), c.runtime, signals=lambda: Signals(mode=self.mode.get()), log=c.log)
        self.service = TaskService(
            Deps(
                self.tasks,
                PolicyEngine(self.access),
                _Retriever(self.indexes),
                self.gateway,
                _Sources(self.indexes),
                c.log,
                clock=c.clock,
                coverage={t: index.coverage for t, index in self.indexes.items()},
                research=ResearchGate(c.egress, c.live_network),
                finance_records=self._domain_records(c, MONEY_DOMAIN),
                health_records=self._domain_records(c, HEALTH_DOMAIN),
                scope=self._open_scope,
            )
        )
        for source_type, index in self.indexes.items():  # a revocation removes the index AND what tasks derived from it
            self.designation.register_purge(source_type, self._purger(source_type, index))
        self.consent = ConsentService(self.designation, self.access, self.indexes, c.os_requester)
        self.clients = c.clients or ClientRegistry(path=c.data_dir / "clients.json")
        self.operations = self._build_operations(c)
        self.web = None if (self.action_gateway is None or c.web_engine is None) else WebReader(c.data_dir, c.web_engine, self.action_gateway, clock=c.clock)
        self.connectors = None if (self.action_gateway is None or c.secrets is None) else ConnectorHub(self.action_gateway, c.secrets, c.connector_adapters)
        self.device_operations = self._build_devices(c)
        self.api = self._build_api(c)
        self.server: UnixServer | None = None
        self._scanned: dict[str, datetime] = {}
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def _build_api(self, c: CoreConfig) -> CoreApi:
        """The edge: the API over the service, the client registry and the optional consent, actions and device parts. With no owner enrolled it starts only with a one-time code (or the development stand-in)."""
        gate = None
        if not self.clients.has_owner():
            if c.bootstrap_code is None and not c.open_bootstrap:
                raise ValueError("no owner client is enrolled: start the Core with a one-time bootstrap code")  # fail closed
            gate = BootstrapGate(c.bootstrap_code) if c.bootstrap_code is not None else None
        return CoreApi(
            self.service,
            self.clients,
            c.log,
            c.clock,
            consent=self.consent,
            bootstrap=gate,
            mode=self.mode,
            ops=self.operations,
            devices=self.device_operations,
            updates=c.updates,
            connectors=self.connectors,
            web=self.web,
        )

    @staticmethod
    def _domain_records(c: CoreConfig, domain: str) -> Callable[[], list[Record]] | None:
        """The records of a restricted domain (Finance, Health), if this Core has a source that can list them (read only when the service has checked the grant)."""
        entry = c.records.get(domain)
        records = getattr(entry[0], "records", None) if entry else None
        return None if records is None else (lambda: list(entry[0].records.values()))  # type: ignore[index, union-attr]

    def _open_scope(self) -> list[str]:
        """The source types a question may use right now: a current grant and the platform's permission, and never a restricted domain (Finance and Health have their own summaries)."""
        rules = load_rules()
        return [t for t in self.indexes if self.access.permitted(t) and not rules.is_restricted(t)]

    def _build_devices(self, c: CoreConfig) -> DeviceOperations:
        """Device pairing and revocation: the Core's own identity key (created once, mode 0600) and the directory of paired devices."""
        identity = CoreIdentity(c.data_dir / "identity.key")
        return DeviceOperations(DeviceDirectory(self.clients, identity, c.data_dir / "devices.json", c.clock), identity.public_key)

    def _build_operations(self, c: CoreConfig) -> Operations | None:
        """The owner's own edits store, the Action Gateway over it and the sync service: present only when the Core was given a key for the store."""
        self.edits: RecordStore | None = None
        self.action_gateway: ActionGateway | None = None
        if c.edits_key is None:
            return None
        self.edits = RecordStore(c.data_dir / "edits.db", c.edits_key, frozenset({"calendar", "contacts", "notes", "travel"}), c.clock)
        audit = AuditFile(c.data_dir / "actions-audit.jsonl")
        history = audit.load()
        if history is None:
            c.log.emit(
                "api.request", "service", "actions-audit", error_code="internal_error"
            )  # a history that does not verify: no actions are served until the owner looks at it
            self.edits.close()
            self.edits = None
            return None
        gateway = ActionGateway(c.clock, audit, history)
        self.action_gateway = gateway
        register_record_actions(gateway, self.edits, c.outbox, c.erase)
        edits = self.edits

        def version_of(record_id: str) -> int | None:
            try:
                return edits.get(record_id, include_deleted=True).version
            except StoreError:
                return None

        return Operations(gateway, SyncService(gateway, self.clients, version_of), self.edits)

    def _purger(self, source_type: str, index: Any) -> Callable[[], None]:
        def purge() -> None:
            self._scanned.pop(source_type, None)  # a new grant starts from an empty index and a fresh scan at once
            index.purge()
            self.service.purge_source_type(source_type)

        return purge

    # -- running -------------------------------------------------------------------------------------------------------------------------------
    def start(self) -> str:
        """Finish owed purges, recover interrupted tasks, bind the socket and start the worker. Returns the socket path."""
        self.designation.run_pending_purges()
        self.service.recover()
        self.server = serve_unix(self.config.socket_path, self.api, self.config.allowed_uids)
        if self.connectors is not None:
            threading.Thread(
                target=self.connectors.verify_all, daemon=True
            ).start()  # connected services are checked in the background; none may act before it answers ok
        for target in (self.server.serve_forever, self._work):
            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            self._threads.append(thread)
        return str(self.config.socket_path)

    def tick(self) -> None:
        """One round of background work: expire what is overdue, run a queued task, and take one bounded slice of each index that is currently permitted."""
        self.service.expire_due()
        for task_id in self.tasks.ids_in(("queued",)):
            self.service.run(task_id)
        self._refresh_adapter_types()
        critical = self._disk_critical()
        for source_type, index in self.indexes.items():
            if not self.access.permitted(source_type):  # nothing is scanned or read without a current grant and platform permission
                self._scanned.pop(source_type, None)
                continue
            if critical:  # the disk is nearly full: no new items are taken in (the pause is shown in coverage); nothing already stored is touched, and questions are still answered
                index.pause_growth("disk_pressure")
                continue
            now = self.clock()
            last = self._scanned.get(source_type)
            if last is None or (now - last).total_seconds() >= RESCAN_SECONDS:
                index.scan()
                self._scanned[source_type] = now
            index.run(INDEX_SLICE)

    def _refresh_adapter_types(self) -> None:
        """The record domains the owner may designate: all of them, except that Finance and Health wait for a passed restore drill when the Core was told to require one."""
        c = self.config
        rules = load_rules()
        held_back = c.require_restore_drill and not drill_passed(c.data_dir, c.clock)
        self.designation.allow_adapter_types(name for name in c.records if not (held_back and rules.is_restricted(name)))

    def _disk_critical(self) -> bool:
        total, _used, free = self.config.disk_usage(self.config.data_dir)
        return pressure_of(free, total) == "critical"

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # noqa: BLE001  (the worker never dies; a failing round is simply tried again)
                self.config.log.emit("api.request", "service", "worker-loop", error_code="internal_error")
            self._stop.wait(0.05)

    def _release_lock(self) -> None:
        fd, self._lock_fd = self._lock_fd, -1
        if fd >= 0:
            os.close(fd)

    def close(self) -> None:
        self._stop.set()
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        for thread in self._threads:
            thread.join(5)
        for index in self.indexes.values():
            index.close()
        for closer in self.config.closers:
            closer()
        self.tasks.close()
        if self.edits is not None:
            self.edits.close()
        self.designation.close()
        self._release_lock()
