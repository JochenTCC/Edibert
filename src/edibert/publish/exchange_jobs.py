"""Catalog exchange inside the publisher loop (backlog ``0.1.d``, client follow-ups).

Three jobs, each switched on in ``publish.json`` (``exchange``): report use of the published tariffs (one request
per tariff at a random time of the day), ask the status of their database versions once a day, and load the
catalog package once a week or when the current one nears ``valid_until``. They run beside the prices: a failure
is logged and retried an hour later, it never takes a price offline. A package is imported only when nothing is
lost silently: a locally entered monthly rate or a tariff the publisher uses that the package would drop holds the
import back, and the editor's import dialog decides. When it is imported the publisher reloads its tariffs.

What the jobs know survives a restart in ``exchange_state.json`` in the data folder, so a restart neither reports
twice nor asks again early. The verified database is loaded when an access key is set, else the free one; a
catalog that came from the verified database is never replaced by a free package.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from edibert.catalog_import import (
    PACKAGE_INFO_KEY,
    REMOVED,
    apply_package_import,
    plan_package_import,
    write_catalog_pair,
)
from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.exchange import (
    ExchangeClient,
    StatusEntry,
    install_secret,
    plan_usage_reports,
    usage_pseudonym,
)
from edibert.fileformat import GRID_CATALOG_FILE, write_json_atomic
from edibert.package import verify_package
from edibert.publish.config import ExchangeSettings, TariffRef
from edibert.store import USER_PREFIX
from edibert.tariff import DbRef

log = logging.getLogger(__name__)

STATE_FILE = "exchange_state.json"
STATE_FORMAT = 1
STATUS_EVERY = timedelta(days=1)
PACKAGE_EVERY = timedelta(days=7)
PACKAGE_BEFORE_EXPIRY = timedelta(days=7)
RETRY_AFTER = timedelta(hours=1)
REPORT_DAY = timedelta(days=1)
JOB_REPORT, JOB_STATUS, JOB_PACKAGE = "report_use", "status", "packages"


@dataclass
class ExchangeState:
    """The jobs' memory; ``None`` times mean "due now"."""

    report_until: datetime | None = None
    pending: list[dict[str, str]] = field(default_factory=list)  # {send_at, db_id, version}: reports still to send
    status_next: datetime | None = None
    status_at: datetime | None = None
    status: list[dict[str, Any]] = field(default_factory=list)
    package_next: datetime | None = None
    package_held: dict[str, Any] | None = None  # the warning of the last held package

    def to_dict(self) -> dict[str, Any]:
        def iso(value: datetime | None) -> str | None:
            return value.isoformat() if value else None

        return {
            "state_format": STATE_FORMAT,
            "report_until": iso(self.report_until), "pending": self.pending,
            "status_next": iso(self.status_next), "status_at": iso(self.status_at), "status": self.status,
            "package_next": iso(self.package_next), "package_held": self.package_held,
        }  # fmt: skip


def _when(raw: Mapping[str, Any], key: str) -> datetime | None:
    value = raw.get(key)
    return None if value is None else datetime.fromisoformat(value)


def load_state(path: Path) -> ExchangeState:
    """The saved state, or a fresh one when there is no file yet. A broken file is an error, never reset silently."""
    if not path.exists():
        return ExchangeState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("state_format") != STATE_FORMAT:
            raise ValueError(f"state_format={raw.get('state_format')!r}")
        return ExchangeState(
            _when(raw, "report_until"), list(raw.get("pending") or []),
            _when(raw, "status_next"), _when(raw, "status_at"), list(raw.get("status") or []),
            _when(raw, "package_next"), raw.get("package_held"),
        )  # fmt: skip
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc


def _status_dict(entry: StatusEntry) -> dict[str, Any]:
    return {
        "db_id": entry.db_id, "version": entry.version, "known": entry.known, "reliable": entry.reliable,
        "installations_12m": entry.installations_12m, "latest_version": entry.latest_version,
        "latest_valid_from": entry.latest_valid_from.isoformat() if entry.latest_valid_from else None,
    }  # fmt: skip


@dataclass
class TickResult:
    notes: list[EdibertWarning] = field(default_factory=list)
    imported: bool = False  # the catalog files were replaced: reload the tariffs


class CatalogExchange:
    def __init__(
        self,
        client: ExchangeClient,
        settings: ExchangeSettings,
        data_dir: Path,
        catalog: Path | None,
        published: tuple[TariffRef, ...],
        refs: Callable[[], Mapping[TariffRef, DbRef]],
        *,
        trusted_keys: Mapping[str, str] | None = None,
        planner: Callable[..., list] = plan_usage_reports,
    ) -> None:
        if settings.packages and catalog is None:
            raise EdibertError(ErrorCode.VALUE_INVALID, "exchange.packages needs a catalog file (--catalog) to import into.",
                               field="exchange.packages", value=True)  # fmt: skip
        self.client = client
        self.settings = settings
        self.data_dir = data_dir
        self.catalog = catalog
        self.published = published  # a package that removes one of these catalog tariffs is held back
        self.trusted_keys = trusted_keys
        self.planner = planner
        self.state_path = data_dir / STATE_FILE
        self.state = load_state(self.state_path)
        self._refs = refs
        self.refs: dict[TariffRef, DbRef] = dict(refs())  # database version of each published tariff

    @property
    def database(self) -> str:
        return "verified" if self.client.config.access_key else "free"

    # -- one tick ---------------------------------------------------------------------------------

    def tick(self, now: datetime) -> TickResult:
        result = TickResult()
        jobs = (
            (self.settings.packages, JOB_PACKAGE, self._packages),
            (self.settings.status, JOB_STATUS, self._status),
            (self.settings.report_use, JOB_REPORT, self._reports),
        )
        for enabled, name, job in jobs:
            if not enabled:
                continue
            try:
                job(now, result)
            except EdibertError as err:
                log.warning("Exchange job %s failed: %s", name, err)
                result.notes.append(EdibertWarning(WarningCode.EXCHANGE_JOB_FAILED, f"{name}: {err}", {"job": name, "code": str(err.code)}))
        self._save()
        return result

    def _save(self) -> None:
        write_json_atomic(self.state_path, self.state.to_dict())

    # -- report use -------------------------------------------------------------------------------

    def _reports(self, now: datetime, result: TickResult) -> None:
        state = self.state
        if state.report_until is None or now >= state.report_until:
            plan = self.planner(list(self.refs.values()), install_secret(self.data_dir), now)
            state.pending = [{"send_at": item.send_at.isoformat(), "db_id": item.db_id, "version": item.version} for item in plan]
            state.report_until = now + REPORT_DAY
        if not state.pending:
            return
        secret = install_secret(self.data_dir)
        while state.pending and datetime.fromisoformat(state.pending[0]["send_at"]) <= now:
            item = state.pending[0]
            self.client.report_usage(item["db_id"], item["version"], usage_pseudonym(secret, item["db_id"]))
            state.pending.pop(0)  # only after the server took it; a failure keeps it for the next tick
            self._save()

    # -- status -----------------------------------------------------------------------------------

    def _status(self, now: datetime, result: TickResult) -> None:
        state = self.state
        if state.status_next is not None and now < state.status_next:
            return
        state.status_next = now + RETRY_AFTER
        pairs = sorted({(ref.id, ref.version) for ref in self.refs.values()})
        entries = self.client.query_status(pairs) if pairs else []
        state.status = [_status_dict(entry) for entry in entries]
        state.status_at = now
        state.status_next = now + STATUS_EVERY

    def status_block(self, ref: TariffRef) -> dict[str, Any] | None:
        """The ``catalog`` attribute of one published tariff: its database version and the last known status."""
        db_ref = self.refs.get(ref)
        if db_ref is None:
            return None
        block: dict[str, Any] = {"database": db_ref.database, "db_id": db_ref.id, "version": db_ref.version}
        if not self.settings.status:
            return block
        found = next((item for item in self.state.status if (item["db_id"], item["version"]) == (db_ref.id, db_ref.version)), None)
        block["checked_at"] = self.state.status_at.isoformat() if self.state.status_at and found else None
        if found is None:
            return block
        newer = found["known"] and found["latest_version"] is not None and found["latest_version"] != found["version"]
        block.update({
            "known": found["known"], "reliable": found["reliable"], "installations_12m": found["installations_12m"],
            "newer_version": newer, "newer_valid_from": found["latest_valid_from"] if newer else None,
        })  # fmt: skip
        return block

    # -- catalog package --------------------------------------------------------------------------

    def _read(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc

    def _hold(self, result: TickResult, note: EdibertWarning) -> None:
        log.warning("Catalog package held back: %s", note.message)
        self.state.package_held = {"code": str(note.code), "params": dict(note.params)}
        result.notes.append(note)

    def _packages(self, now: datetime, result: TickResult) -> None:
        state = self.state
        if state.package_next is not None and now < state.package_next:
            if state.package_held:
                code = WarningCode(state.package_held["code"])
                result.notes.append(EdibertWarning(code, "catalog package still held back", state.package_held["params"]))
            return
        state.package_next = now + RETRY_AFTER
        assert self.catalog is not None  # checked in __init__
        grid_path = self.catalog.parent / GRID_CATALOG_FILE
        local = self._read(self.catalog)
        info = (local or {}).get(PACKAGE_INFO_KEY) or {}
        current, offered = info.get("database"), self.database
        if current == "verified" and offered == "free":
            state.package_next = now + PACKAGE_EVERY
            self._hold(result, EdibertWarning(WarningCode.PACKAGE_HELD_DATABASE, "verified catalog, no access key",
                                              {"current": current, "offered": offered}))  # fmt: skip
            return
        document = self.client.fetch_package(offered, info.get("package_id") if current == offered else None)
        if document is None:
            state.package_held = None
            state.package_next = self._next_package_check(now, info.get("valid_until"))
            return
        package = verify_package(document, trusted_keys=self.trusted_keys, today=now.date())
        manifest = package.manifest
        plan = plan_package_import(package, local, self._read(grid_path))
        state.package_next = self._next_package_check(now, manifest.valid_until.isoformat())
        used = {f"{ref.direction}/{ref.id}" for ref in self.published if not ref.id.startswith(USER_PREFIX)}
        removed = sorted(item.key for item in plan.changes if item.change == REMOVED and item.key in used)
        if removed:
            self._hold(result, EdibertWarning(WarningCode.PACKAGE_HELD_REMOVES_USED, f"{manifest.package_id} removes {removed}",
                                              {"package_id": manifest.package_id, "entries": ", ".join(removed)}))  # fmt: skip
            return
        if plan.conflicts:
            self._hold(result, EdibertWarning(WarningCode.PACKAGE_HELD_CONFLICTS, f"{manifest.package_id}: {len(plan.conflicts)} conflicts",
                                              {"package_id": manifest.package_id, "count": len(plan.conflicts)}))  # fmt: skip
            return
        tariffs, grid_fees = apply_package_import(plan, {})
        write_catalog_pair(self.catalog, tariffs, grid_path, grid_fees)
        self.refs = dict(self._refs())
        state.package_held = None
        result.notes.extend(package.warnings)
        result.imported = True
        log.info("Imported catalog package %s (%s database).", manifest.package_id, manifest.database)

    @staticmethod
    def _next_package_check(now: datetime, valid_until: str | None) -> datetime:
        """In a week, or earlier when the package expires within it (never sooner than tomorrow)."""
        regular = now + PACKAGE_EVERY
        if not valid_until:
            return regular
        early = datetime.combine(date.fromisoformat(valid_until), time(0), tzinfo=UTC) - PACKAGE_BEFORE_EXPIRY
        return max(now + timedelta(days=1), min(regular, early))
