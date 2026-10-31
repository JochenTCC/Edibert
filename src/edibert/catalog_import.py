"""Import of a verified catalog package (Catalog P5): plan first, then apply with the caller's decisions.

The package replaces ``tariffs.json`` and ``grid_fees.json`` as a whole; ``user_tariffs.json`` and
``user_grid_fees.json`` are never touched. The one thing a replacement could lose silently is a monthly rate
entered locally (a tariff's ``monthly_rates`` row or a row of a monthly reference curve at the root) that the
package does not have or has with another value. Each such row is a conflict; the caller decides per conflict
(:data:`KEEP_LOCAL` or :data:`TAKE_PACKAGE`), and an undecided conflict stops the import.
"""

from __future__ import annotations

import copy
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from edibert._fields import invalid
from edibert.errors import EdibertError, ErrorCode
from edibert.fileformat import write_json_atomic
from edibert.gridfee import parse_grid_fee_catalog
from edibert.package import SECTIONS, CatalogPackage
from edibert.store import parse_tariff_documents

KEEP_LOCAL = "keep_local"
TAKE_PACKAGE = "take_package"
CHOICES = (KEEP_LOCAL, TAKE_PACKAGE)
ADDED, CHANGED, REMOVED = "added", "changed", "removed"
ROOT = "root"
GRID = "grid"
RULE_SET = "rule_set"
PACKAGE_INFO_KEY = "package"  # root key of the imported tariffs.json: which package it came from
PACKAGE_INFO_FIELDS = ("package_id", "issued_at", "valid_until")


@dataclass(frozen=True)
class EntryChange:
    """A catalog entry the import adds, changes or removes; ``key`` is ``import/<id>``, ``export/<id>``,
    ``grid/<area id>`` or ``rule_set/<id>``."""

    key: str
    change: str


@dataclass(frozen=True)
class MonthConflict:
    """A locally entered monthly rate the package would drop or change.

    ``key`` is ``<direction>/<tariff id>/<YYYY-MM>`` or ``root/<curve key>/<YYYY-MM>``; ``package_cent`` is
    ``None`` when the package has no row for that month.
    """

    key: str
    local_cent: float
    package_cent: float | None


@dataclass(frozen=True)
class ImportPlan:
    package: CatalogPackage
    changes: tuple[EntryChange, ...]
    conflicts: tuple[MonthConflict, ...]


def _month_key(row: Mapping[str, Any]) -> str:
    return f"{row['year']}-{int(row['month']):02d}"


def _is_month_table(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(row, dict) and {"year", "month", "tariff_cent_kwh"} <= set(row) for row in value)
    )


def _rows(entries: list[Mapping[str, Any]]) -> dict[str, float]:
    return {_month_key(row): row["tariff_cent_kwh"] for entry in entries for row in entry.get("monthly_rates") or []}


def _grouped(document: Mapping[str, Any] | None, section: str) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for raw in (document or {}).get(section) or []:
        groups.setdefault(str(raw.get("id")), []).append(raw)
    return groups


def _changes(prefix: str, old: Mapping[str, Any], new: Mapping[str, Any]) -> list[EntryChange]:
    result = [EntryChange(f"{prefix}/{key}", ADDED) for key in new if key not in old]
    result += [EntryChange(f"{prefix}/{key}", CHANGED) for key in new if key in old and old[key] != new[key]]
    result += [EntryChange(f"{prefix}/{key}", REMOVED) for key in old if key not in new]
    return result


def _conflicts(prefix: str, local: Mapping[str, float], package: Mapping[str, float]) -> list[MonthConflict]:
    return [
        MonthConflict(f"{prefix}/{month}", cent, package.get(month))
        for month, cent in sorted(local.items())
        if package.get(month) != cent
    ]


def plan_package_import(
    package: CatalogPackage,
    local_tariffs: Mapping[str, Any] | None,
    local_grid_fees: Mapping[str, Any] | None,
) -> ImportPlan:
    """What importing ``package`` over the current catalog documents (``None`` = no file yet) would change."""
    changes: list[EntryChange] = []
    conflicts: list[MonthConflict] = []
    for direction, section in SECTIONS.items():
        old, new = _grouped(local_tariffs, section), _grouped(package.tariffs, section)
        changes += _changes(direction, old, new)
        for tariff_id in old.keys() & new.keys():
            conflicts += _conflicts(f"{direction}/{tariff_id}", _rows(old[tariff_id]), _rows(new[tariff_id]))
    for key, value in (local_tariffs or {}).items():
        if _is_month_table(value):
            package_rows = package.tariffs.get(key)
            package_table = {_month_key(row): row["tariff_cent_kwh"] for row in package_rows or []}
            conflicts += _conflicts(f"{ROOT}/{key}", {_month_key(row): row["tariff_cent_kwh"] for row in value}, package_table)
    old_areas = {str(area.get("id")): area for area in (local_grid_fees or {}).get("areas") or []}
    new_areas = {str(area.get("id")): area for area in package.grid_fees.get("areas") or []}
    changes += _changes(GRID, old_areas, new_areas)
    changes += _changes(RULE_SET, (local_grid_fees or {}).get("rule_sets") or {}, package.grid_fees.get("rule_sets") or {})
    return ImportPlan(package, tuple(changes), tuple(sorted(conflicts, key=lambda item: item.key)))


def _check_resolutions(plan: ImportPlan, resolutions: Mapping[str, str]) -> None:
    keys = {conflict.key for conflict in plan.conflicts}
    for key, choice in resolutions.items():
        if key not in keys:
            raise invalid("resolutions", key)
        if choice not in CHOICES:
            raise invalid(f"resolutions.{key}", choice)
    for conflict in plan.conflicts:
        if conflict.key not in resolutions:
            raise EdibertError(
                ErrorCode.PACKAGE_IMPORT_CONFLICT,
                f"Locally entered monthly rate '{conflict.key}' would be lost; decide keep_local or take_package.",
                conflict=conflict.key,
            )


def _put_row(table: list[dict[str, Any]], month: str, cent: float) -> None:
    year, number = (int(part) for part in month.split("-"))
    table[:] = [row for row in table if (row["year"], row["month"]) != (year, number)]
    table.append({"year": year, "month": number, "tariff_cent_kwh": cent})
    table.sort(key=lambda row: (row["year"], row["month"]))


def _version_for(entries: list[dict[str, Any]], month: str) -> dict[str, Any]:
    """The validity version a kept row belongs to: the one covering the month's first day, else the newest."""
    first = date.fromisoformat(f"{month}-01")
    for entry in entries:
        start, end = entry.get("valid_from"), entry.get("valid_to")
        if (start is None or date.fromisoformat(start) <= first) and (end is None or first <= date.fromisoformat(end)):
            return entry
    return max(entries, key=lambda entry: entry.get("valid_from") or "")


def apply_package_import(plan: ImportPlan, resolutions: Mapping[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The new ``tariffs.json`` and ``grid_fees.json`` documents: the package plus the rows kept locally.

    Every conflict needs a decision (``PACKAGE_IMPORT_CONFLICT``); unknown keys or choices are ``VALUE_INVALID``.
    The result is loaded once more before it is returned, so an import never writes a catalog that does not load.
    """
    _check_resolutions(plan, resolutions)
    tariffs = copy.deepcopy(dict(plan.package.tariffs))
    grid_fees = copy.deepcopy(dict(plan.package.grid_fees))
    for conflict in plan.conflicts:
        if resolutions[conflict.key] != KEEP_LOCAL:
            continue
        scope, name, month = conflict.key.split("/")
        if scope == ROOT:
            _put_row(tariffs.setdefault(name, []), month, conflict.local_cent)
            continue
        entries = [raw for raw in tariffs[SECTIONS[scope]] if raw.get("id") == name]
        _put_row(_version_for(entries, month).setdefault("monthly_rates", []), month, conflict.local_cent)
    manifest = plan.package.manifest
    tariffs[PACKAGE_INFO_KEY] = {
        "package_id": manifest.package_id,
        "issued_at": manifest.issued_at.isoformat(),
        "valid_until": manifest.valid_until.isoformat(),
    }
    parse_tariff_documents(tariffs, None)
    parse_grid_fee_catalog(grid_fees)
    return tariffs, grid_fees


def write_catalog_pair(tariffs_path: Path, tariffs: Mapping[str, Any], grid_path: Path, grid_fees: Mapping[str, Any]) -> None:
    """Write both catalog files: both are written completely to temporary files before either is replaced,
    so a failed write leaves the old pair in place."""
    staged: list[tuple[Path, Path]] = []
    try:
        for path, document in ((grid_path, grid_fees), (tariffs_path, tariffs)):
            path.parent.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            os.close(handle)
            temp = Path(name)
            staged.append((temp, path))
            write_json_atomic(temp, document)
        for temp, path in staged:
            os.replace(temp, path)
    finally:
        for temp, _ in staged:
            temp.unlink(missing_ok=True)
