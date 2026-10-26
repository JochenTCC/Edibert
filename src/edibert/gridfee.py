"""Grid fee (Netznutzungsentgelt) work price: house-profile selection, grid areas, evaluation.

The house profile's ``netznutzung`` field only selects a grid area and states the house-side metering
facts. The areas live in tariff-track files: the catalog ``grid_fees.json`` (Earnie shape) and the user
file ``user_grid_fees.json`` with the same shape and ``user_`` IDs (own work prices, for example the three
levels of section 14a EnWG module 3). Prices are net, cent/kWh.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from edibert._fields import (
    as_dict,
    check_known,
    get_bool,
    get_number,
    get_str,
    invalid,
    missing,
)
from edibert.context import PricingContext
from edibert.errors import EdibertError, ErrorCode
from edibert.fileformat import (
    FORMAT_KEY,
    TARIFF_FORMAT,
    check_tariff_format,
    write_json_atomic,
)
from edibert.rules import (
    STATUSES,
    Rule,
    apply_effect,
    day_info,
    matching_rule,
    parse_rules,
)

METERING = ("unmetered_power", "metered_power")
DEFAULT_INCLUDE_STATUS = ("verordnet",)
SKIP_STATUS = "status"
SKIP_NO_QUARTER_HOUR_METER = "no_quarter_hour_meter"
USER_PREFIX = "user_"
CATALOG = "catalog"
USER = "user"
GRID_HOLIDAY_MODE = "sunday"  # a holiday counts as a Sunday for grid rules; areas have no own holiday setting

CONFIG_FIELDS = ("area_id", "power_metering", "quarter_hour_meter", "include_status")
DOCUMENT_FIELDS = (FORMAT_KEY, "description", "rule_sets", "areas")
AREA_FIELDS = ("id", "label", "land", "base_cent_kwh", "rule_set", "source")


@dataclass(frozen=True)
class GridFeeConfig:
    """The ``netznutzung`` field of a house profile: which grid area, and how the house is metered."""

    area_id: str
    power_metering: str
    quarter_hour_meter: bool
    include_status: tuple[str, ...]


@dataclass(frozen=True)
class GridArea:
    id: str
    label: str
    land: str
    base_cent_kwh: Mapping[str, float]
    rule_set: str | None
    source: str


@dataclass(frozen=True)
class GridFeeCatalog:
    """Areas and rule sets of one or both grid files; ``origin[area_id]`` is ``catalog`` or ``user``."""

    rule_sets: Mapping[str, tuple[Rule, ...]]
    areas: Mapping[str, GridArea]
    origin: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SkippedRule:
    rule_id: str
    reason: str  # SKIP_STATUS or SKIP_NO_QUARTER_HOUR_METER
    detail: str | None = None


@dataclass(frozen=True)
class GridFee:
    """A resolved grid fee: base work price plus the rules that are in effect."""

    area_id: str
    base_cent_kwh: float
    rules: tuple[Rule, ...]
    skipped: tuple[SkippedRule, ...]

    def work_cent(self, local: datetime, ctx: PricingContext) -> tuple[float, str | None]:
        """Net work price and the id of the rule that applied for the slot at ``local``."""
        if not self.rules:
            return self.base_cent_kwh, None
        day = day_info(self.rules, GRID_HOLIDAY_MODE, frozenset(), local, ctx)
        rule = matching_rule(
            self.rules, local, day, holiday_mode=GRID_HOLIDAY_MODE, epex_cent=None, tariff_id="netznutzung"
        )
        if rule is None:
            return self.base_cent_kwh, None
        return apply_effect(self.base_cent_kwh, rule.effect, rule.id), rule.id


def parse_grid_fee_config(raw: object, label: str = "netznutzung") -> GridFeeConfig:
    """Validate the house-profile field strictly; ``area_id`` is required (there is no implicit "no fee")."""
    if raw is None:
        raise missing(f"{label}.area_id")
    data = as_dict(raw, label)
    check_known(data, CONFIG_FIELDS, label)
    area_id = get_str(data, "area_id", label, required=True)
    assert area_id is not None
    metering = get_str(data, "power_metering", label) or METERING[0]
    if metering not in METERING:
        raise invalid(f"{label}.power_metering", metering)
    include = data.get("include_status", list(DEFAULT_INCLUDE_STATUS))
    if not isinstance(include, list) or any(item not in STATUSES for item in include):
        raise invalid(f"{label}.include_status", include)
    return GridFeeConfig(
        area_id=area_id,
        power_metering=metering,
        quarter_hour_meter=get_bool(data, "quarter_hour_meter", label, False),
        include_status=tuple(include),
    )


def _check_grid_id(grid_id: str, origin: str) -> None:
    if origin == USER and not grid_id.startswith(USER_PREFIX):
        raise EdibertError(
            ErrorCode.GRID_ID_PREFIX_MISSING,
            f"User grid ID '{grid_id}' must start with '{USER_PREFIX}'.",
            grid_id=grid_id,
        )
    if origin == CATALOG and grid_id.startswith(USER_PREFIX):
        raise EdibertError(
            ErrorCode.GRID_ID_PREFIX_RESERVED,
            f"Catalog grid ID '{grid_id}' uses the reserved prefix '{USER_PREFIX}'.",
            grid_id=grid_id,
        )


def _collision(grid_id: str) -> EdibertError:
    return EdibertError(ErrorCode.GRID_ID_COLLISION, f"Grid ID '{grid_id}' is used more than once.", grid_id=grid_id)


def _parse_area(raw: object, where: str, rule_sets: Mapping[str, tuple[Rule, ...]]) -> GridArea:
    data = as_dict(raw, where)
    area_id = get_str(data, "id", where, required=True)
    assert area_id is not None
    check_known(data, AREA_FIELDS, where)
    raw_base = data.get("base_cent_kwh")
    if raw_base is None:
        raise missing(f"{where}.base_cent_kwh")
    base = as_dict(raw_base, f"{where}.base_cent_kwh")
    check_known(base, METERING, f"{where}.base_cent_kwh")
    prices = {key: get_number(base, key, f"{where}.base_cent_kwh", required=True, minimum=0) for key in METERING}
    rule_set = get_str(data, "rule_set", where)
    if rule_set is not None and rule_set not in rule_sets:
        raise invalid(f"{where}.rule_set", rule_set)
    return GridArea(
        id=area_id,
        label=get_str(data, "label", where) or area_id,
        land=(get_str(data, "land", where) or "AT").upper(),
        base_cent_kwh={key: value for key, value in prices.items() if value is not None},
        rule_set=rule_set,
        source=get_str(data, "source", where) or "",
    )


def parse_grid_fee_catalog(doc: object, origin: str = CATALOG, where: str | None = None) -> GridFeeCatalog:
    """Validate ``grid_fees.json`` (``origin="catalog"``) or ``user_grid_fees.json`` (``origin="user"``).

    Both need a supported ``tariff_format``. Catalog rules need a ``status``; user rules may omit it and
    then always apply. Area and rule-set IDs follow the ``user_`` prefix rule of their origin; an area may
    only use a rule set of its own file.
    """
    if origin not in (CATALOG, USER):
        raise invalid("origin", origin)
    where = where or ("grid_fees" if origin == CATALOG else "user_grid_fees")
    data = as_dict(doc, where)
    check_tariff_format(data, where)
    check_known(data, DOCUMENT_FIELDS, where)
    raw_sets = as_dict(data.get("rule_sets", {}), f"{where}.rule_sets")
    rule_sets: dict[str, tuple[Rule, ...]] = {}
    for set_id, items in raw_sets.items():
        _check_grid_id(set_id, origin)
        rules = parse_rules(items, f"{where}.rule_sets[{set_id}]", grid=True)
        for rule in rules:
            if origin == CATALOG and rule.status is None:
                raise missing(f"{where}.rule_sets[{set_id}].rules[{rule.id}].status")
        rule_sets[set_id] = rules
    areas_raw = data.get("areas", [])
    if not isinstance(areas_raw, list):
        raise invalid(f"{where}.areas", areas_raw)
    areas: dict[str, GridArea] = {}
    for index, item in enumerate(areas_raw):
        area = _parse_area(item, f"{where}.areas[{index}]", rule_sets)
        _check_grid_id(area.id, origin)
        if area.id in areas:
            raise _collision(area.id)
        areas[area.id] = area
    return GridFeeCatalog(rule_sets, areas, dict.fromkeys(areas, origin))


def merge_grid_fee_catalogs(catalog: GridFeeCatalog | None, user: GridFeeCatalog | None) -> GridFeeCatalog:
    """One view of catalog and user areas; an ID (area or rule set) in both is ``GRID_ID_COLLISION``."""
    rule_sets: dict[str, tuple[Rule, ...]] = {}
    areas: dict[str, GridArea] = {}
    origin: dict[str, str] = {}
    for part in (catalog, user):
        if part is None:
            continue
        for set_id, rules in part.rule_sets.items():
            if set_id in rule_sets:
                raise _collision(set_id)
            rule_sets[set_id] = rules
        for area_id, area in part.areas.items():
            if area_id in areas:
                raise _collision(area_id)
            areas[area_id] = area
            origin[area_id] = part.origin[area_id]
    return GridFeeCatalog(rule_sets, areas, origin)


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        return as_dict(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, ValueError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read file '{path}': {exc}", path=str(path)) from exc


def load_grid_fee_catalog(path: Path) -> GridFeeCatalog:
    """The catalog file ``grid_fees.json`` alone."""
    return parse_grid_fee_catalog(_read_json(path), CATALOG, str(path))


def load_grid_fees(catalog: Path | None = None, user: Path | None = None) -> GridFeeCatalog:
    """Catalog and user grid file as one view. A missing user file means no user areas."""
    catalog_part = load_grid_fee_catalog(catalog) if catalog is not None else None
    user_part = None
    if user is not None and user.exists():
        user_part = parse_grid_fee_catalog(_read_json(user), USER, str(user))
    return merge_grid_fee_catalogs(catalog_part, user_part)


def load_grid_fee_config(path: Path) -> GridFeeConfig:
    """Config from a file: either the bare object or a document with a ``netznutzung`` key."""
    doc = _read_json(path)
    return parse_grid_fee_config(doc.get("netznutzung", doc))


def flat_user_grid_area(
    area_id: str, base_cent_kwh: float, *, label: str | None = None, land: str | None = None
) -> dict[str, Any]:
    """A user area with one work price for both metering types and no rule set (an own flat grid fee)."""
    area: dict[str, Any] = {"id": area_id}
    if label is not None:
        area["label"] = label
    if land is not None:
        area["land"] = land
    area["base_cent_kwh"] = dict.fromkeys(METERING, base_cent_kwh)
    return area


def empty_user_grid_document() -> dict[str, Any]:
    return {FORMAT_KEY: TARIFF_FORMAT, "rule_sets": {}, "areas": []}


def put_user_grid_area(document: Mapping[str, Any], area: Mapping[str, Any]) -> dict[str, Any]:
    """A copy of a user grid document with ``area`` added or replaced (same ID); the result is validated."""
    result = copy.deepcopy(dict(as_dict(document, "user_grid_fees")))
    area_id = as_dict(area, "user_grid_fees.area").get("id")
    areas = result.get("areas", [])
    if not isinstance(areas, list):
        raise invalid("user_grid_fees.areas", areas)
    kept = [item for item in areas if not (isinstance(item, dict) and item.get("id") == area_id)]
    result["areas"] = [*kept, copy.deepcopy(dict(area))]
    parse_grid_fee_catalog(result, USER)
    return result


def save_user_grid_area(path: Path, area: Mapping[str, Any]) -> None:
    """Add or replace one area in ``user_grid_fees.json``; other entries stay untouched.

    A missing file is created with the current ``tariff_format``. The whole file is validated before it is
    written, so an invalid area or an unmigrated file leaves the file unchanged.
    """
    document = _read_json(path) if path.exists() else empty_user_grid_document()
    write_json_atomic(path, put_user_grid_area(document, area))


def _filter_rules(rules: tuple[Rule, ...], config: GridFeeConfig) -> tuple[list[Rule], list[SkippedRule]]:
    active: list[Rule] = []
    skipped: list[SkippedRule] = []
    for rule in rules:
        if rule.status is not None and rule.status not in config.include_status:
            skipped.append(SkippedRule(rule.id, SKIP_STATUS, rule.status))
        elif "quarter_hour_meter" in rule.requires and not config.quarter_hour_meter:
            skipped.append(SkippedRule(rule.id, SKIP_NO_QUARTER_HOUR_METER))
        elif rule.effect.value is None:
            raise EdibertError(
                ErrorCode.RULE_VALUE_MISSING, f"Included rule '{rule.id}' has no value.", rule_id=rule.id
            )
        else:
            active.append(rule)
    return active, skipped


def resolve_grid_fee(config: GridFeeConfig, catalog: GridFeeCatalog) -> GridFee:
    """Combine the profile field and the selected area (catalog or user) into an evaluable grid fee.

    The base price comes from the area (by metering type) and the area's rule set applies.
    """
    if config.area_id not in catalog.areas:
        raise EdibertError(
            ErrorCode.GRID_AREA_UNKNOWN, f"Unknown grid area '{config.area_id}'.", area_id=config.area_id
        )
    area = catalog.areas[config.area_id]
    base = area.base_cent_kwh[config.power_metering]
    rules = catalog.rule_sets.get(area.rule_set, ()) if area.rule_set else ()
    active, skipped = _filter_rules(rules, config)
    return GridFee(config.area_id, float(base), tuple(active), tuple(skipped))
