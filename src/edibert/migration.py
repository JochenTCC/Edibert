"""Migration of the tariff-track files to the current ``tariff_format``: pure, documents in, documents out.

The caller reads the files, passes them as ``{file name: document}`` (a missing file is left out or
``None``), shows the questions, and writes the returned documents itself (with its own backup). Nothing
here touches the disk. What the migration does:

* tags untagged files with ``tariff_format`` and removes the old ``earnie_data_model`` key;
* creates user grid areas in ``user_grid_fees.json`` from areas handed in by the caller (Earnie takes them
  from the house profiles, see :func:`edibert.gridfee.flat_user_grid_area`);
* removes ``database`` from the ``db_ref`` of user tariffs (contract v2 has one tariff database; the key is
  ``DB_REF_LEGACY`` on load, never ignored);
* asks for ``vat_percent`` on user tariffs without one (gross or net); the country's standard rate is offered as a
  prefill, but only an answer is ever written.

Problems the user has to solve outside the migration are blockers; a blocked run changes nothing.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from edibert._fields import as_dict, invalid
from edibert.errors import EdibertError, ErrorCode
from edibert.fileformat import (
    CATALOG_FILE,
    FORMAT_KEY,
    GRID_CATALOG_FILE,
    TARIFF_FORMAT,
    TARIFF_TRACK_FILES,
    USER_FILE,
    USER_GRID_FILE,
    check_tariff_format,
)
from edibert.gridfee import (
    CATALOG,
    USER,
    empty_user_grid_document,
    merge_grid_fee_catalogs,
    parse_grid_fee_catalog,
)
from edibert.store import parse_tariff_documents
from edibert.tariff import EXPORT, IMPORT, LEGACY_DB_REF_FIELD

LEGACY_KEY = "earnie_data_model"  # Earnie's data-model stamp; read only here, removed by the migration
STANDARD_VAT_PERCENT = {"AT": 20.0, "DE": 19.0, "CH": 8.1}  # prefill for the VAT question, never written unasked
QUESTION_VAT_PERCENT = "VAT_PERCENT"  # UI text: question.VAT_PERCENT
SECTIONS = {IMPORT: "import_tariffs", EXPORT: "export_tariffs"}

Docs = Mapping[str, Mapping[str, Any] | None]


@dataclass(frozen=True)
class MigrationQuestion:
    """Input the migration needs. ``id`` is the key of the answer; the UI shows ``question.<code>`` with ``params``."""

    id: str  # e.g. "vat_percent:import:user_my_tariff"
    code: str  # QUESTION_VAT_PERCENT
    file: str
    kind: str  # "number"
    required: bool
    default: float | None  # prefill to offer; None if there is none
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MigrationBlocker:
    """A problem the migration cannot solve; the UI shows ``error.<code>`` with ``params``."""

    code: ErrorCode
    file: str | None
    params: Mapping[str, Any]
    message: str  # English, for logs


@dataclass(frozen=True)
class MigrationPlan:
    """What :func:`migrate` would do. ``current`` holds each given file's ``tariff_format`` (``None`` = untagged)."""

    current: Mapping[str, Any]
    to_format: int
    changed_files: tuple[str, ...]  # files migrate() writes, assuming the questions are answered
    questions: tuple[MigrationQuestion, ...]
    blockers: tuple[MigrationBlocker, ...]

    @property
    def needed(self) -> bool:
        """True if the files need a migration run (changes, questions or blockers)."""
        return bool(self.changed_files or self.questions or self.blockers)

    @property
    def can_run(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class MigrationResult:
    """The documents after the migration (all given files; changed ones listed in ``changed_files``).

    With blockers nothing is changed: ``docs`` are copies of the input and ``changed_files`` is empty.
    """

    docs: dict[str, dict[str, Any]]
    changed_files: tuple[str, ...]
    blockers: tuple[MigrationBlocker, ...]


@dataclass
class _Run:
    docs: dict[str, dict[str, Any]]
    questions: list[MigrationQuestion] = field(default_factory=list)
    blockers: list[MigrationBlocker] = field(default_factory=list)
    pending_vat: list[tuple[str, int, float | None]] = field(default_factory=list)  # direction, index, prefill

    def block(self, error: EdibertError, file: str | None) -> None:
        self.blockers.append(MigrationBlocker(error.code, file, dict(error.params), str(error)))

    def blocked(self, file: str) -> bool:
        return any(blocker.file == file for blocker in self.blockers)


def _copy_docs(docs: Docs) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, document in docs.items():
        if name not in TARIFF_TRACK_FILES:
            raise invalid("docs", name)
        if document is not None:
            result[name] = copy.deepcopy(dict(as_dict(document, name)))
    return result


def _tag(run: _Run) -> None:
    for name, document in list(run.docs.items()):
        document.pop(LEGACY_KEY, None)
        if FORMAT_KEY not in document:
            run.docs[name] = {FORMAT_KEY: TARIFF_FORMAT, **document}
            continue
        try:
            check_tariff_format(document, name)
        except EdibertError as error:
            run.block(error, name)


def _add_user_grid_areas(run: _Run, areas: Sequence[Mapping[str, Any]]) -> None:
    if not areas or run.blocked(USER_GRID_FILE):
        return
    document = run.docs.setdefault(USER_GRID_FILE, empty_user_grid_document())
    existing = document.setdefault("areas", [])
    if not isinstance(existing, list):
        run.block(invalid(f"{USER_GRID_FILE}.areas", existing), USER_GRID_FILE)
        return
    for raw in areas:
        area = dict(as_dict(raw, "user_grid_areas"))
        same = [item for item in existing if isinstance(item, dict) and item.get("id") == area.get("id")]
        if not same:
            existing.append(copy.deepcopy(area))
        elif same[0] != area:  # an identical area is already there: nothing to do (a second run is a no-op)
            grid_id = str(area.get("id"))
            run.block(
                EdibertError(
                    ErrorCode.GRID_ID_COLLISION,
                    f"User grid area '{grid_id}' exists with other values.",
                    grid_id=grid_id,
                ),
                USER_GRID_FILE,
            )


def _drop_legacy_db_ref(run: _Run) -> None:
    document = run.docs.get(USER_FILE)
    if document is None or run.blocked(USER_FILE):
        return
    for section in SECTIONS.values():
        entries = document.get(section)
        if not isinstance(entries, list):
            continue  # a wrong shape is reported by the validation
        for entry in entries:
            ref = entry.get("db_ref") if isinstance(entry, dict) else None
            if isinstance(ref, dict):
                ref.pop(LEGACY_DB_REF_FIELD, None)


def _vat_answer(question_id: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise invalid(question_id, value)
    return float(value)


def _ask_vat(run: _Run, answers: Mapping[str, Any] | None) -> None:
    document = run.docs.get(USER_FILE)
    if document is None or run.blocked(USER_FILE):
        return
    for direction, section in SECTIONS.items():
        entries = document.get(section)
        if not isinstance(entries, list):
            continue  # a wrong shape is reported by the validation
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or entry.get("vat_percent") is not None:
                continue
            tariff_id = str(entry.get("id"))
            question_id = f"vat_percent:{direction}:{tariff_id}"
            land = entry.get("land")
            prefill = STANDARD_VAT_PERCENT.get(land.upper()) if isinstance(land, str) else None
            if answers is None:
                run.pending_vat.append((direction, index, prefill))
                params = {"tariff_id": tariff_id, "label": str(entry.get("label", tariff_id)), "direction": direction}
                params["prices"] = "gross" if entry.get("prices_include_vat", True) is True else "net"
                params["land"] = land if isinstance(land, str) else ""
                run.questions.append(
                    MigrationQuestion(question_id, QUESTION_VAT_PERCENT, USER_FILE, "number", True, prefill, params)
                )
            elif question_id in answers:
                entry["vat_percent"] = _vat_answer(question_id, answers[question_id])
            else:
                raise EdibertError(
                    ErrorCode.MIGRATION_ANSWER_MISSING,
                    f"Migration question '{question_id}' has no answer.",
                    question_id=question_id,
                )


def _probe_docs(run: _Run) -> dict[str, dict[str, Any]]:
    """The documents as validated: pending VAT questions filled with their prefill (or 0), for checking only."""
    if not run.pending_vat:
        return run.docs
    probe = copy.deepcopy(run.docs)
    for direction, index, prefill in run.pending_vat:
        probe[USER_FILE][SECTIONS[direction]][index]["vat_percent"] = prefill if prefill is not None else 0.0
    return probe


def _check(run: _Run, file: str, check: Callable[[], object]) -> bool:
    try:
        check()
    except EdibertError as error:
        run.block(error, file)
        return False
    return True


def _validate(run: _Run) -> None:
    """The migrated files must load; the first problem per file becomes a blocker."""
    docs = _probe_docs(run)

    def present(name: str) -> dict[str, Any] | None:
        return None if run.blocked(name) else docs.get(name)

    catalog, user = present(CATALOG_FILE), present(USER_FILE)
    ok = catalog is None or _check(run, CATALOG_FILE, lambda: parse_tariff_documents(catalog, None))
    ok = (user is None or _check(run, USER_FILE, lambda: parse_tariff_documents(None, user))) and ok
    if ok and catalog is not None and user is not None:
        _check(run, USER_FILE, lambda: parse_tariff_documents(catalog, user))
    grid, user_grid = present(GRID_CATALOG_FILE), present(USER_GRID_FILE)
    parsed: dict[str, Any] = {}
    for name, document, origin in ((GRID_CATALOG_FILE, grid, CATALOG), (USER_GRID_FILE, user_grid, USER)):
        if document is not None:
            _check(run, name, lambda d=document, o=origin, n=name: parsed.setdefault(n, parse_grid_fee_catalog(d, o, n)))
    if len(parsed) == 2:
        _check(run, USER_GRID_FILE, lambda: merge_grid_fee_catalogs(parsed[GRID_CATALOG_FILE], parsed[USER_GRID_FILE]))


def _run(docs: Docs, answers: Mapping[str, Any] | None, user_grid_areas: Sequence[Mapping[str, Any]]) -> _Run:
    run = _Run(_copy_docs(docs))
    _tag(run)
    _add_user_grid_areas(run, user_grid_areas)
    _drop_legacy_db_ref(run)
    _ask_vat(run, answers)
    _validate(run)
    return run


def _changed(before: Docs, after: Mapping[str, dict[str, Any]]) -> tuple[str, ...]:
    return tuple(name for name in TARIFF_TRACK_FILES if name in after and before.get(name) != after[name])


def plan_migration(docs: Docs, *, user_grid_areas: Sequence[Mapping[str, Any]] = ()) -> MigrationPlan:
    """What :func:`migrate` would change, which questions it needs answered, and what blocks it."""
    run = _run(docs, None, user_grid_areas)
    changed = _changed(docs, run.docs)
    if run.pending_vat and USER_FILE not in changed:
        changed = tuple(name for name in TARIFF_TRACK_FILES if name in changed or name == USER_FILE)
    current = {name: document.get(FORMAT_KEY) for name, document in docs.items() if document is not None}
    return MigrationPlan(current, TARIFF_FORMAT, changed, tuple(run.questions), tuple(run.blockers))


def migrate(
    docs: Docs,
    answers: Mapping[str, Any] | None = None,
    *,
    user_grid_areas: Sequence[Mapping[str, Any]] = (),
) -> MigrationResult:
    """Bring the tariff-track files to the current ``tariff_format``.

    ``answers`` maps question IDs from :func:`plan_migration` to values; a required question without an
    answer is ``MIGRATION_ANSWER_MISSING``, an invalid answer ``VALUE_INVALID``. Running it on migrated files
    changes nothing.
    """
    run = _run(docs, answers or {}, user_grid_areas)
    if run.blockers:
        return MigrationResult(_copy_docs(docs), (), tuple(run.blockers))
    return MigrationResult(run.docs, _changed(docs, run.docs), ())

