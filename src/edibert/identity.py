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
from edibert.gridfee import parse_grid_fee_catalog
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
AREA_IGNORED = ("$comment", "id", "label", "note", "source")


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


def _raw_plain(value: Any) -> Any:
    """Raw JSON with numbers as floats and display fields removed (grid areas are hashed as written)."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Mapping):
        return {key: _raw_plain(item) for key, item in value.items() if key not in AREA_IGNORED}
    if isinstance(value, list):
        return [_raw_plain(item) for item in value]
    raise TypeError(f"not JSON data: {value!r}")


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


def db_ref_for(raw: Mapping[str, Any], direction: str, database: str) -> dict[str, str]:
    """The ``db_ref`` a copy of this database entry carries: database, database ID and version."""
    return {"database": database, "id": tariff_identity(raw, direction), "version": tariff_version(raw, direction)}


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


def grid_area_version(area: Mapping[str, Any], rule_sets: Mapping[str, Any]) -> str:
    """Version of a catalog grid area: SHA-256 (hex) over its prices and the rules of its ``rule_set``."""
    rule_set = area.get("rule_set")
    sets = {rule_set: rule_sets[rule_set]} if rule_set in rule_sets else {}
    parse_grid_fee_catalog({FORMAT_KEY: TARIFF_FORMAT, "rule_sets": sets, "areas": [dict(area)]})  # validate
    return _digest(_raw_plain({"area": dict(area), "rules": sets.get(rule_set, [])}))
