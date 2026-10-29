"""Catalog tariffs for "copy from catalog": reading, type keys, filters and order (no UI)."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from edibert._fields import as_dict, invalid
from edibert.editor.model import TYPE_BY_KIND
from edibert.editor.userstore import SECTIONS
from edibert.errors import EdibertError, ErrorCode
from edibert.tariff import EXPORT, IMPORT, SPOT_EXPORT_TYPES, SPOT_IMPORT_TYPES

SPOT_TYPES = {IMPORT: SPOT_IMPORT_TYPES, EXPORT: SPOT_EXPORT_TYPES}
MTUS = ("15min", "60min")


@dataclass(frozen=True)
class CatalogEntry:
    direction: str
    raw: Mapping[str, Any]

    @property
    def label(self) -> str:
        return str(self.raw.get("label") or self.raw["id"])

    @property
    def land(self) -> str | None:
        return self.raw.get("land")


def _read(path: Path) -> Mapping[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc
    return as_dict(document, str(path))


def _covers(raw: Mapping[str, Any], day: date) -> bool:
    start, end = raw.get("valid_from"), raw.get("valid_to")
    return (start is None or date.fromisoformat(start) <= day) and (end is None or day <= date.fromisoformat(end))


def _current(versions: list[Mapping[str, Any]], day: date) -> Mapping[str, Any]:
    """Of several validity versions of one ID: the one valid on ``day``, else the newest."""
    for raw in versions:
        if _covers(raw, day):
            return raw
    return max(versions, key=lambda raw: raw.get("valid_from") or "")


def read_catalog(path: Path, today: date | None = None) -> list[CatalogEntry]:
    """All import and export tariffs of a catalog file, in file order; of an ID with several validity
    versions only the one valid ``today`` (default: the local date), else the newest."""
    document = _read(path)
    day = today or date.today()
    entries: list[CatalogEntry] = []
    for direction in (IMPORT, EXPORT):
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for raw in document.get(SECTIONS[direction], []):
            groups.setdefault(str(raw.get("id")), []).append(raw)
        entries.extend(CatalogEntry(direction, _current(versions, day)) for versions in groups.values())
    return entries


def catalog_database(path: Path) -> str | None:
    """The tariff database a catalog file came from (root ``package.database`` of an imported package);
    ``None`` for a catalog that was not imported from a package (the seed)."""
    package = _read(path).get("package")
    return None if package is None else str(as_dict(package, f"{path}.package").get("database"))


def settlement_interval(raw: Mapping[str, Any], direction: str) -> str | None:
    """``15min`` / ``60min`` for a market-price tariff, ``None`` where the interval does not apply."""
    if raw.get("type") not in SPOT_TYPES[direction]:
        return None
    mtu = raw.get("settlement_mtu", "15min")
    if mtu not in MTUS:
        raise invalid(f"{raw.get('id')}.settlement_mtu", mtu)
    return mtu


def type_key(raw: Mapping[str, Any], direction: str) -> str:
    """Filter key in the editor's wording: price kind, for market prices with the interval (``spot:15min``)."""
    tariff_type = raw.get("type")
    mtu = settlement_interval(raw, direction)
    if mtu is not None:
        return f"spot:{mtu}"
    for kind, mapped in TYPE_BY_KIND[direction].items():
        if mapped == tariff_type:
            return kind
    raise invalid(f"{raw.get('id')}.type", tariff_type)


def applies_to_house(entry: CatalogEntry, land: str | None, region: str | None) -> bool:
    """A tariff with ``regions`` applies only there; without, to its whole land.

    ``region`` is the house's; without one (or for a tariff of another land) the regions are not checked.
    """
    regions = entry.raw.get("regions")
    if not regions or not region or entry.land != land:
        return True
    return region in regions


def filter_entries(
    entries: Iterable[CatalogEntry],
    *,
    land: str | None,
    direction: str | None,
    kind: str | None,
    house_land: str | None,
    house_region: str | None,
) -> list[CatalogEntry]:
    """Entries of ``land`` / ``direction`` / type key ``kind`` (``None`` = any) that apply to the house.

    Sorted by label; without a direction filter all import tariffs come first, then all export tariffs.
    """
    chosen = [
        entry
        for entry in entries
        if (land is None or entry.land == land)
        and (direction is None or entry.direction == direction)
        and (kind is None or type_key(entry.raw, entry.direction) == kind)
        and applies_to_house(entry, house_land, house_region)
    ]
    order = {IMPORT: 0, EXPORT: 1}
    return sorted(chosen, key=lambda entry: (order[entry.direction], entry.label.casefold()))


def lands_of(entries: Iterable[CatalogEntry]) -> list[str]:
    return sorted({entry.land for entry in entries if entry.land})


def type_keys_of(entries: Iterable[CatalogEntry]) -> list[str]:
    """Type keys present, in the order of the editor's price kinds."""
    present = {type_key(entry.raw, entry.direction) for entry in entries}
    order = ["fixed", *(f"spot:{mtu}" for mtu in MTUS), "monthly"]
    return [key for key in order if key in present]
