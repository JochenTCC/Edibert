"""Tariff database identity and version: a stable ID per tariff or grid area and a hash per price state.

The identity names *which* tariff an entry is (land, direction and catalog ID; the catalog ID stands for
supplier and product). The version is a SHA-256 over the price-relevant values in canonical JSON, so the
same prices give the same version however the file is written, and every price change gives a new one.
User tariffs have no identity of their own: the tariff database assigns one when a tariff is shared.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping
from datetime import date, time
from typing import Any

from edibert._fields import as_dict, get_str, missing
from edibert.errors import EdibertError, ErrorCode
from edibert.fileformat import FORMAT_KEY, TARIFF_FORMAT
from edibert.gridfee import USER, area_document, parse_grid_fee_catalog
from edibert.rules import Rule
from edibert.store import USER_PREFIX
from edibert.tariff import EXPORT, IMPORT, Tariff, parse_tariff

GRID = "grid"
ALL_MONTHS = frozenset(range(1, 13))
# What decides a price. Display and bookkeeping fields (ID, label, supplier, notes, source, regions,
# requirements, last check, origin) never change a price, so they never change the version.
PRICE_FIELDS = (
    "direction", "type", "land", "currency", "settlement_fee_cent_kwh", "markup_percent", "prices_include_vat",
    "vat_percent", "settlement_mtu", "fix_cent_kwh", "k_push_cent", "feed_in_fee_factor", "feed_in_fix_cent",
    "monthly_rates", "fees", "rules", "price_floor_cent_kwh", "price_cap_cent_kwh", "holiday_mode",
    "extra_holiday_dates", "valid_from", "valid_to",
)  # fmt: skip
# Base-price fields each kind of tariff reads (see ``tariff._base_cent``); the others are ignored for it, so a
# value the type never uses (the editor drops it) does not change the version.
BASE_FIELDS = ("settlement_fee_cent_kwh", "markup_percent", "fix_cent_kwh", "k_push_cent", "feed_in_fee_factor",
               "feed_in_fix_cent", "monthly_rates")  # fmt: skip
USED_BASE_FIELDS = {
    (IMPORT, True): ("settlement_fee_cent_kwh", "markup_percent"),
    (EXPORT, True): ("settlement_fee_cent_kwh", "feed_in_fee_factor", "feed_in_fix_cent"),
    (IMPORT, "fixed_cent"): ("fix_cent_kwh",),
    (EXPORT, "fixed"): ("k_push_cent",),
    (IMPORT, "monthly_table"): ("monthly_rates",),
    (EXPORT, "monthly_table"): ("monthly_rates",),
}
RULE_IGNORED = ("id", "label", "source", "note")
CHARGE_IGNORED = ("id", "label", "source", "note")


def _plain(value: Any) -> Any:
    """Parsed values as JSON data: numbers as floats, sets sorted, dates as ISO text."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, Rule):
        fields = {f.name: getattr(value, f.name) for f in dataclasses.fields(value) if f.name not in RULE_IGNORED}
        if fields["months"] == ALL_MONTHS:  # every month and no month filter mean the same
            fields["months"] = None
        return {key: _plain(item) for key, item in fields.items()}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(item) for item in value), key=repr)
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, Mapping):
        return sorted(([_plain(key), _plain(item)] for key, item in value.items()), key=repr)
    raise TypeError(f"no canonical form for {value!r}")


def _digest(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tariff_identity(raw: Mapping[str, Any], direction: str) -> str:
    """Database ID of a catalog tariff: ``<LAND>/<direction>/<catalog id>``.

    A user tariff (``user_`` ID) has none (``DB_ID_UNAVAILABLE``); a tariff without ``land`` cannot get one.
    """
    tariff = parse_tariff(raw, direction)
    if tariff.id.startswith(USER_PREFIX):
        raise EdibertError(
            ErrorCode.DB_ID_UNAVAILABLE,
            f"User tariff '{tariff.id}' has no database ID; the database assigns one when it is shared.",
            tariff_id=tariff.id,
        )
    if tariff.land is None:
        raise missing(f"{tariff.id}.land")
    return f"{tariff.land.upper()}/{direction}/{tariff.id}"


def version_of(tariff: Tariff) -> str:
    """Version of a parsed tariff entry: SHA-256 (hex) over its price-relevant values."""
    used = USED_BASE_FIELDS[(tariff.direction, True if tariff.is_spot else tariff.type)]
    names = [name for name in PRICE_FIELDS if name not in BASE_FIELDS or name in used]
    return _digest({name: _plain(getattr(tariff, name)) for name in names})


def tariff_version(raw: Mapping[str, Any], direction: str) -> str:
    """Version of a raw tariff entry (validated first). Defaults written out or left away give the same
    version, as do number spellings (``20`` / ``20.0``), key order, rule IDs and labels."""
    return version_of(parse_tariff(raw, direction))


def differs_from_db(raw: Mapping[str, Any], direction: str) -> bool | None:
    """``None`` without ``db_ref``; otherwise True when the entry's prices are no longer the referenced version."""
    tariff = parse_tariff(raw, direction)
    if tariff.db_ref is None:
        return None
    return version_of(tariff) != tariff.db_ref.version


def db_ref_for(raw: Mapping[str, Any], direction: str) -> dict[str, str]:
    """The ``db_ref`` a copy of this database entry carries: database ID and version."""
    return {"id": tariff_identity(raw, direction), "version": tariff_version(raw, direction)}


def grid_area_identity(area: Mapping[str, Any]) -> str:
    """Database ID of a catalog grid area: ``<LAND>/grid/<area id>``."""
    data = as_dict(area, "area")
    area_id = get_str(data, "id", "area", required=True)
    assert area_id is not None
    if area_id.startswith(USER_PREFIX):
        raise EdibertError(
            ErrorCode.DB_ID_UNAVAILABLE, f"User grid area '{area_id}' has no database ID.", tariff_id=area_id
        )
    land = get_str(data, "land", area_id)
    if land is None:
        raise missing(f"{area_id}.land")
    return f"{land.upper()}/{GRID}/{area_id}"


def _parts_plain(parts: Any) -> list[Any]:
    return [_plain(part.by_metering) for part in parts]


def entry_version(entry: Mapping[str, Any]) -> str:
    """Version of an inlined grid area (``gridfee.area_document``): SHA-256 (hex) over the **parsed** prices: land,
    work price, rules of its rule set (as for tariffs, without ``id``, ``label``, ``source``, ``note``), components,
    fixed amounts and capacity charges (without their names), and the levies of its levy set. So a copy under another
    ID or set name, or saved unchanged by the editor, keeps the version, and every price change makes a new one."""
    area = dict(as_dict(entry.get("area"), "area"))
    rules, levies = list(entry.get("rules") or []), entry.get("levies")
    probe_id = "user_probe"  # IDs never enter a version; validated as a user area (rule statuses optional)
    document: dict[str, Any] = {FORMAT_KEY: TARIFF_FORMAT, "rule_sets": {}, "levy_sets": {}, "areas": []}
    probe = {key: value for key, value in area.items() if key not in ("rule_set", "levy_set", "db_ref", "check", "id")}
    probe["id"] = probe_id
    if rules:
        document["rule_sets"][probe_id] = rules
        probe["rule_set"] = probe_id
    if levies:
        document["levy_sets"][f"{probe_id}_levies"] = dict(levies)
        probe["levy_set"] = f"{probe_id}_levies"
    document["areas"].append(probe)
    parsed = parse_grid_fee_catalog(document, USER, "grid_area")
    found = parsed.areas[probe_id]
    levy_set = parsed.levy_sets.get(found.levy_set) if found.levy_set else None
    capacity = [
        {f.name: _plain(getattr(charge, f.name)) for f in dataclasses.fields(charge) if f.name not in CHARGE_IGNORED}
        for charge in found.capacity_charges
    ]
    return _digest({
        "land": found.land,
        "base_cent_kwh": _plain(found.base_cent_kwh),
        "rules": [_plain(rule) for rule in parsed.rule_sets.get(probe_id, ())],
        "components": _parts_plain(found.components),
        "fixed_eur_year": _parts_plain(found.fixed),
        "capacity_charges": capacity,
        "levy_components": _parts_plain(levy_set.components) if levy_set else [],
        "levy_fixed_eur_year": _parts_plain(levy_set.fixed) if levy_set else [],
    })


def grid_area_version(area: Mapping[str, Any], rule_sets: Mapping[str, Any], levy_sets: Mapping[str, Any] | None = None) -> str:
    """Version of a grid area of a document: its prices with the rules of its ``rule_set`` and the levies of its
    ``levy_set`` (a ``levy_set`` without ``levy_sets`` is ``VALUE_INVALID``)."""
    document = {"rule_sets": dict(rule_sets), "levy_sets": dict(levy_sets or {}), "areas": [dict(area)]}
    return entry_version(area_document(document, str(area.get("id"))))


def grid_document_versions(document: Mapping[str, Any]) -> dict[str, str]:
    """``{area id: version}`` of every area of a grid document."""
    data = as_dict(document, "grid_fees")
    return {str(area.get("id")): entry_version(area_document(data, str(area.get("id")))) for area in data.get("areas") or []}


def grid_db_ref_for(document: Mapping[str, Any], area_id: str) -> dict[str, str]:
    """The ``db_ref`` a copy of the catalog grid area ``area_id`` carries: database ID and version."""
    entry = area_document(document, area_id)
    return {"id": grid_area_identity(entry["area"]), "version": entry_version(entry)}


def grid_differs_from_db(document: Mapping[str, Any], area_id: str) -> bool | None:
    """``None`` when the area has no ``db_ref``, else whether its prices are no longer the referenced version."""
    entry = area_document(document, area_id)
    ref = entry["area"].get("db_ref")
    if ref is None:
        return None
    return entry_version(entry) != as_dict(ref, f"{area_id}.db_ref").get("version")
