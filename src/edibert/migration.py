"""Migration of the tariff-track files to the current ``tariff_format``: pure, documents in, documents out.

The caller reads the files, passes them as ``{file name: document}`` (a missing file is left out or
``None``), shows the questions, and writes the returned documents itself (with its own backup). Nothing
here touches the disk. What the migration does:

* tags untagged files with ``tariff_format`` and removes the old ``earnie_data_model`` key;
* creates user grid areas in ``user_grid_fees.json`` from areas handed in by the caller (Earnie takes them
  from the house profiles, see :func:`edibert.gridfee.flat_user_grid_area`);
* removes ``database`` from the ``db_ref`` of user tariffs (contract v2 has one tariff database; the key is
  ``DB_REF_LEGACY`` on load, never ignored);
* moves ``grid_monthly_fee_eur`` of user tariffs into the grid area the caller names (``grid_fee_area``) as a fixed
  yearly amount (0.1.d2: the grid base fee belongs to the grid area). It never guesses: one value, net of the
  tariff's VAT, times twelve, into a user area; several different values, no area, or a catalog area are blockers
  (``GRID_MONTHLY_FEE_AMBIGUOUS``, ``GRID_MONTHLY_FEE_NO_TARGET``). A value of 0 is removed without a move;
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
from edibert.store import USER_PREFIX, parse_tariff_documents
from edibert.tariff import EXPORT, IMPORT, LEGACY_DB_REF_FIELD, LEGACY_GRID_FEE_FIELD

LEGACY_KEY = "earnie_data_model"  # Earnie's data-model stamp; read only here, removed by the migration
STANDARD_VAT_PERCENT = {"AT": 20.0, "DE": 19.0, "CH": 8.1}  # prefill for the VAT question, never written unasked
QUESTION_VAT_PERCENT = "VAT_PERCENT"  # UI text: question.VAT_PERCENT
SECTIONS = {IMPORT: "import_tariffs", EXPORT: "export_tariffs"}
MOVED_FEE_ID = "grid_base_fee"  # ID of the fixed amount the moved ``grid_monthly_fee_eur`` becomes
MOVED_FEE_LABEL = "Grid base fee"

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
    moves_grid_fee: bool = False  # planned only: the grid fee move waits for the VAT answers
    probe_docs: dict[str, dict[str, Any]] | None = None  # planned only: prefills and the move applied, for checking

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


def _add_user_grid_rule_sets(run: _Run, rule_sets: Mapping[str, Sequence[Any]]) -> None:
    """Rule sets handed in with the areas (the editor's own grid rules); identical = no change, other = blocker."""
    if not rule_sets or run.blocked(USER_GRID_FILE):
        return
    document = run.docs.setdefault(USER_GRID_FILE, empty_user_grid_document())
    existing = document.setdefault("rule_sets", {})
    if not isinstance(existing, dict):
        run.block(invalid(f"{USER_GRID_FILE}.rule_sets", existing), USER_GRID_FILE)
        return
    for set_id, rules in rule_sets.items():
        if set_id not in existing:
            existing[set_id] = copy.deepcopy(list(rules))
        elif existing[set_id] != list(rules):
            run.block(
                EdibertError(ErrorCode.GRID_ID_COLLISION, f"User rule set '{set_id}' exists with other rules.", grid_id=set_id),
                USER_GRID_FILE,
            )


def _net_year(entry: Mapping[str, Any]) -> float | None:
    """``grid_monthly_fee_eur`` of a tariff as a net yearly amount (the tariff's price convention, times twelve)."""
    value = entry.get(LEGACY_GRID_FEE_FIELD)
    vat = entry.get("vat_percent")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None  # a wrong value is reported by the validation
    if entry.get("prices_include_vat", True) is True:
        if isinstance(vat, bool) or not isinstance(vat, (int, float)):
            return None  # the VAT question comes first
        return round(value * 12 / (1 + vat / 100), 4)
    return round(value * 12.0, 4)


def _target_area(run: _Run, area_id: str | None) -> dict[str, Any] | None:
    """The user area the fee moves into; a catalog area (or none) is never a target."""
    if area_id is None or not area_id.startswith(USER_PREFIX) or run.blocked(USER_GRID_FILE):
        return None
    areas = (run.docs.get(USER_GRID_FILE) or {}).get("areas")
    if not isinstance(areas, list):
        return None
    return next((item for item in areas if isinstance(item, dict) and item.get("id") == area_id), None)


def _move_grid_monthly_fee(run: _Run, grid_fee_area: str | None) -> None:
    """Move ``grid_monthly_fee_eur`` from the user tariffs into the fixed amounts of the user area ``grid_fee_area``."""
    document = run.docs.get(USER_FILE)
    if document is None or run.blocked(USER_FILE):
        return
    carriers: list[tuple[dict[str, Any], float | None]] = []
    for section in SECTIONS.values():
        entries = document.get(section)
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and LEGACY_GRID_FEE_FIELD in entry:
                carriers.append((entry, _net_year(entry)))
    if not carriers:
        return
    moving = [(entry, value) for entry, value in carriers if entry.get(LEGACY_GRID_FEE_FIELD) != 0]
    if any(value is None for _, value in moving):
        return  # an invalid value: the validation names it (GRID_MONTHLY_FEE_LEGACY), nothing is moved
    if moving:
        ids = ", ".join(str(entry.get("id")) for entry, _ in moving)
        values = sorted({value for _, value in moving if value is not None})
        target = _target_area(run, grid_fee_area)
        if target is None:
            run.block(
                EdibertError(
                    ErrorCode.GRID_MONTHLY_FEE_NO_TARGET,
                    f"Tariffs {ids} carry a monthly grid fee, but there is no own grid area to move it to "
                    f"(house area: {grid_fee_area or '-'}).",
                    tariff_ids=ids,
                    area_id=grid_fee_area or "-",
                ),
                USER_FILE,
            )
            return
        fixed = target.setdefault("fixed_eur_year", [])
        present = [item.get("eur_year") for item in fixed if isinstance(item, dict) and item.get("id") == MOVED_FEE_ID]
        if len(values) > 1 or (present and present[0] != values[0]):
            shown = ", ".join(f"{value:g}" for value in [*values, *present])
            run.block(
                EdibertError(
                    ErrorCode.GRID_MONTHLY_FEE_AMBIGUOUS,
                    f"Tariffs {ids} carry different grid base fees ({shown} EUR/year net); decide the area's value.",
                    tariff_ids=ids,
                    values=shown,
                ),
                USER_FILE,
            )
            return
        if not present:
            fixed.append({"id": MOVED_FEE_ID, "label": MOVED_FEE_LABEL, "eur_year": values[0]})
    for entry, _ in carriers:
        entry.pop(LEGACY_GRID_FEE_FIELD)


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
    if run.probe_docs is not None:
        return run.probe_docs
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


def _run(
    docs: Docs,
    answers: Mapping[str, Any] | None,
    user_grid_areas: Sequence[Mapping[str, Any]],
    user_grid_rule_sets: Mapping[str, Sequence[Any]],
    grid_fee_area: str | None,
) -> _Run:
    run = _Run(_copy_docs(docs))
    _tag(run)
    _add_user_grid_rule_sets(run, user_grid_rule_sets)
    _add_user_grid_areas(run, user_grid_areas)
    _drop_legacy_db_ref(run)
    _ask_vat(run, answers)
    if not run.pending_vat:
        _move_grid_monthly_fee(run, grid_fee_area)
    else:  # the net amount needs the VAT answers: the plan checks the move with the prefills and moves nothing
        probe = _Run(_probe_docs(run))
        _move_grid_monthly_fee(probe, grid_fee_area)
        run.blockers.extend(probe.blockers)
        if probe.docs.get(USER_GRID_FILE) != run.docs.get(USER_GRID_FILE):
            run.moves_grid_fee = True
        run.probe_docs = probe.docs
    _validate(run)
    return run


def _changed(before: Docs, after: Mapping[str, dict[str, Any]]) -> tuple[str, ...]:
    return tuple(name for name in TARIFF_TRACK_FILES if name in after and before.get(name) != after[name])


def plan_migration(
    docs: Docs,
    *,
    user_grid_areas: Sequence[Mapping[str, Any]] = (),
    user_grid_rule_sets: Mapping[str, Sequence[Any]] | None = None,
    grid_fee_area: str | None = None,
) -> MigrationPlan:
    """What :func:`migrate` would change, which questions it needs answered, and what blocks it.

    ``grid_fee_area`` names the user grid area the house uses: the only place a ``grid_monthly_fee_eur`` of the
    user tariffs moves to. ``None`` (no own area, or the house uses a catalog area) blocks such a move.
    """
    run = _run(docs, None, user_grid_areas, user_grid_rule_sets or {}, grid_fee_area)
    changed = _changed(docs, run.docs)
    pending = {USER_FILE} if run.pending_vat else set()
    if run.moves_grid_fee:
        pending.add(USER_GRID_FILE)
    if pending - set(changed):
        changed = tuple(name for name in TARIFF_TRACK_FILES if name in changed or name in pending)
    current = {name: document.get(FORMAT_KEY) for name, document in docs.items() if document is not None}
    return MigrationPlan(current, TARIFF_FORMAT, changed, tuple(run.questions), tuple(run.blockers))


def migrate(
    docs: Docs,
    answers: Mapping[str, Any] | None = None,
    *,
    user_grid_areas: Sequence[Mapping[str, Any]] = (),
    user_grid_rule_sets: Mapping[str, Sequence[Any]] | None = None,
    grid_fee_area: str | None = None,
) -> MigrationResult:
    """Bring the tariff-track files to the current ``tariff_format``.

    ``answers`` maps question IDs from :func:`plan_migration` to values; a required question without an
    answer is ``MIGRATION_ANSWER_MISSING``, an invalid answer ``VALUE_INVALID``. Running it on migrated files
    changes nothing.
    """
    run = _run(docs, answers or {}, user_grid_areas, user_grid_rule_sets or {}, grid_fee_area)
    if run.blockers:
        return MigrationResult(_copy_docs(docs), (), tuple(run.blockers))
    return MigrationResult(run.docs, _changed(docs, run.docs), ())

