"""Grid fee (Netznutzungsentgelt): house-profile selection, grid areas, evaluation.

The house profile's ``netznutzung`` field only selects a grid area and states the house-side metering
facts. The areas live in tariff-track files: the catalog ``grid_fees.json`` (Earnie shape) and the user
file ``user_grid_fees.json`` with the same shape and ``user_`` IDs (own work prices, for example the three
levels of section 14a EnWG module 3). An area has the work price (``base_cent_kwh``, the only part rules
change), further per-kWh ``components`` (grid loss charge), ``fixed_eur_year`` amounts (grid base fee) and an
optional ``levy_set``: the national levies of the file's ``levy_sets``, defined once and shared by many areas.
Prices are net: cent/kWh per slot, EUR per year for the fixed amounts (spec section 5a).
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
from edibert.capacity import CapacityCharge, parse_capacity_charges
from edibert.context import PricingContext, region_codes
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
from edibert.tariff import CatalogCheck, DbRef, _parse_db_ref, parse_check

METERING = ("unmetered_power", "metered_power")
DEFAULT_INCLUDE_STATUS = ("verordnet",)
SKIP_STATUS = "status"
SKIP_NO_QUARTER_HOUR_METER = "no_quarter_hour_meter"
USER_PREFIX = "user_"
CATALOG = "catalog"
USER = "user"
GRID_FILE_SHARE = "grid"  # direction name of a grid area in sharing, use reports and the database ID
GRID_HOLIDAY_MODE = "sunday"  # a holiday counts as a Sunday for grid rules; areas have no own holiday setting

CONFIG_FIELDS = ("area_id", "power_metering", "quarter_hour_meter", "include_status")
DOCUMENT_FIELDS = (FORMAT_KEY, "description", "rule_sets", "levy_sets", "areas")
AREA_FIELDS = (
    "id", "label", "land", "regions", "operator", "base_cent_kwh", "rule_set", "components", "fixed_eur_year",
    "levy_set", "source", "capacity_charges", "db_ref", "check",
)  # fmt: skip
LEVY_SET_FIELDS = ("label", "components", "fixed_eur_year", "source", "note")
COMPONENT_FIELDS = ("id", "label", "cent_kwh", "source", "note")
FIXED_FIELDS = ("id", "label", "eur_year", "source", "note")
WORK_PART = "work"  # breakdown key of the work price (base after rules); component IDs must not use it


@dataclass(frozen=True)
class GridPart:
    """A per-kWh component (cent/kWh) or a fixed amount (EUR per year) of an area or its levy set.

    ``by_metering`` maps a metering type to the value; ``None`` means the value is not modeled for that type (for
    example the grid base fee of metered power, which is a power price per kW): selecting it is an error.
    """

    id: str
    label: str
    by_metering: Mapping[str, float | None]
    from_levy_set: bool = False


@dataclass(frozen=True)
class LevySet:
    """National levies set per Netzebene (renewables contribution and flat fee), defined once per file."""

    id: str
    label: str
    components: tuple[GridPart, ...]
    fixed: tuple[GridPart, ...]


@dataclass(frozen=True)
class ResolvedPart:
    """A component or fixed amount for the house's metering type: cent/kWh or EUR per year, net."""

    id: str
    label: str
    value: float


@dataclass(frozen=True)
class GridSlot:
    """The grid fee of one slot: work price after rules plus the components, net cent/kWh."""

    work_cent: float
    rule_id: str | None
    components: tuple[tuple[str, float], ...]

    @property
    def total_cent(self) -> float:
        return self.work_cent + sum(cent for _, cent in self.components)

    @property
    def breakdown(self) -> tuple[tuple[str, float], ...]:
        return ((WORK_PART, self.work_cent), *self.components)


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
    capacity_charges: tuple[CapacityCharge, ...] = ()
    regions: tuple[str, ...] = ()  # federal states / cantons the area lies in; empty = not narrowed (whole land)
    operator: str | None = None  # network operator, display only
    components: tuple[GridPart, ...] = ()
    fixed: tuple[GridPart, ...] = ()
    levy_set: str | None = None
    db_ref: DbRef | None = None  # user areas: the database entry the area was copied from
    check: CatalogCheck | None = None  # catalog areas of a package: the check the database signed


@dataclass(frozen=True)
class GridFeeCatalog:
    """Areas, rule sets and levy sets of one or both grid files; ``origin[area_id]`` is ``catalog`` or ``user``."""

    rule_sets: Mapping[str, tuple[Rule, ...]]
    areas: Mapping[str, GridArea]
    origin: Mapping[str, str] = field(default_factory=dict)
    levy_sets: Mapping[str, LevySet] = field(default_factory=dict)

    def areas_for(self, land: str, region: str | None) -> list[GridArea]:
        """Areas of ``land`` that lie in ``region`` (an area without ``regions`` matches every region), by label."""
        found = [
            area for area in self.areas.values()
            if area.land == land.upper() and (not area.regions or (region is not None and region in area.regions))
        ]  # fmt: skip
        return sorted(found, key=lambda area: (area.label, area.id))


@dataclass(frozen=True)
class SkippedRule:
    rule_id: str
    reason: str  # SKIP_STATUS or SKIP_NO_QUARTER_HOUR_METER
    detail: str | None = None


@dataclass(frozen=True)
class GridFee:
    """A resolved grid fee: base work price plus the rules that are in effect.

    ``capacity`` holds the capacity-charge entries in effect (section 5b), ``capacity_skipped`` the entries left
    out by status (ID to status). ``quarter_hour_meter`` says whether the house can supply the month-to-date peak.
    """

    area_id: str
    base_cent_kwh: float
    rules: tuple[Rule, ...]
    skipped: tuple[SkippedRule, ...]
    capacity: tuple[CapacityCharge, ...] = ()
    capacity_skipped: Mapping[str, str] = field(default_factory=dict)
    quarter_hour_meter: bool = True
    components: tuple[ResolvedPart, ...] = ()  # cent/kWh next to the work price; rules never change them
    fixed: tuple[ResolvedPart, ...] = ()  # EUR per year, net; never folded into a slot price

    @property
    def fixed_eur_year(self) -> float:
        return sum(part.value for part in self.fixed)

    def slot(self, local: datetime, ctx: PricingContext) -> GridSlot:
        """Work price after rules, the rule that applied and the components for the slot at ``local``."""
        work, rule_id = self.work_cent(local, ctx)
        return GridSlot(work, rule_id, tuple((part.id, part.value) for part in self.components))

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


def _by_metering(value: object, where: str, *, allow_none: bool) -> dict[str, float | None]:
    """A value per metering type: one number for both, or ``{unmetered_power, metered_power}`` (both keys).

    With ``allow_none`` a key may be ``null``: not modeled for that metering type (selecting it is an error).
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = get_number({"v": value}, "v", where, minimum=0)
        return dict.fromkeys(METERING, number)
    data = as_dict(value, where)
    check_known(data, METERING, where)
    result: dict[str, float | None] = {}
    for key in METERING:
        if key not in data:
            raise missing(f"{where}.{key}")
        if data[key] is None and allow_none:
            result[key] = None
            continue
        result[key] = get_number(data, key, where, required=True, minimum=0)
    if all(item is None for item in result.values()):
        raise invalid(where, value)
    return result


def _parse_parts(raw: object, where: str, value_key: str, fields: tuple[str, ...], from_levy_set: bool) -> tuple[GridPart, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise invalid(where, raw)
    parts: list[GridPart] = []
    for index, item in enumerate(raw):
        path = f"{where}[{index}]"
        data = as_dict(item, path)
        check_known(data, fields, path)
        part_id = get_str(data, "id", path, required=True)
        assert part_id is not None
        if value_key not in data:
            raise missing(f"{path}.{value_key}")
        parts.append(
            GridPart(
                part_id,
                get_str(data, "label", path) or part_id,
                _by_metering(data[value_key], f"{path}.{value_key}", allow_none=True),
                from_levy_set,
            )
        )
    return tuple(parts)


def _check_part_ids(parts: tuple[GridPart, ...], where: str) -> None:
    """IDs of the components and fixed amounts of an area (with its levy set) name the lines of a breakdown."""
    seen: set[str] = set()
    for part in parts:
        if part.id == WORK_PART or part.id in seen:
            raise invalid(f"{where}.id", part.id)
        seen.add(part.id)


def _parse_levy_set(set_id: str, raw: object, where: str) -> LevySet:
    data = as_dict(raw, where)
    check_known(data, LEVY_SET_FIELDS, where)
    components = _parse_parts(data.get("components"), f"{where}.components", "cent_kwh", COMPONENT_FIELDS, True)
    fixed = _parse_parts(data.get("fixed_eur_year"), f"{where}.fixed_eur_year", "eur_year", FIXED_FIELDS, True)
    if not components and not fixed:
        raise missing(f"{where}.components")
    _check_part_ids(components, f"{where}.components")
    _check_part_ids(fixed, f"{where}.fixed_eur_year")
    return LevySet(set_id, get_str(data, "label", where) or set_id, components, fixed)


def _parse_area_regions(data: Mapping[str, Any], land: str, where: str) -> tuple[str, ...]:
    """``regions``: subdivision codes of the area's land (the house field ``region``); absent = whole land."""
    value = data.get("regions")
    if value is None:
        return ()
    if not isinstance(value, list) or not value or len(set(value)) != len(value):
        raise invalid(f"{where}.regions", value)
    known = region_codes(land)
    for code in value:
        if code not in known:
            raise invalid(f"{where}.regions", code)
    return tuple(value)


def _parse_area(
    raw: object,
    where: str,
    rule_sets: Mapping[str, tuple[Rule, ...]],
    levy_sets: Mapping[str, LevySet],
    *,
    require_status: bool,
) -> GridArea:
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
    levy_set = get_str(data, "levy_set", where)
    if levy_set is not None and levy_set not in levy_sets:
        raise invalid(f"{where}.levy_set", levy_set)
    land = (get_str(data, "land", where) or "AT").upper()
    components = _parse_parts(data.get("components"), f"{where}.components", "cent_kwh", COMPONENT_FIELDS, False)
    fixed = _parse_parts(data.get("fixed_eur_year"), f"{where}.fixed_eur_year", "eur_year", FIXED_FIELDS, False)
    levies = levy_sets.get(levy_set) if levy_set else None
    _check_part_ids(components + (levies.components if levies else ()), f"{where}.components")
    _check_part_ids(fixed + (levies.fixed if levies else ()), f"{where}.fixed_eur_year")
    return GridArea(
        id=area_id,
        label=get_str(data, "label", where) or area_id,
        land=land,
        base_cent_kwh={key: value for key, value in prices.items() if value is not None},
        rule_set=rule_set,
        source=get_str(data, "source", where) or "",
        capacity_charges=parse_capacity_charges(
            data.get("capacity_charges", []), f"{where}.capacity_charges", require_status=require_status
        ),
        regions=_parse_area_regions(data, land, where),
        operator=get_str(data, "operator", where),
        components=components,
        fixed=fixed,
        levy_set=levy_set,
        db_ref=_parse_db_ref(data.get("db_ref"), f"{where}.db_ref"),
        check=parse_check(data.get("check"), f"{where}.check"),
    )


def parse_grid_fee_catalog(doc: object, origin: str = CATALOG, where: str | None = None) -> GridFeeCatalog:
    """Validate ``grid_fees.json`` (``origin="catalog"``) or ``user_grid_fees.json`` (``origin="user"``).

    Both need a supported ``tariff_format``. Catalog rules and capacity charges need a ``status``; user
    entries may omit it and then always apply. Area and rule-set IDs follow the ``user_`` prefix rule of their origin; an area may
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
    raw_levies = as_dict(data.get("levy_sets", {}), f"{where}.levy_sets")
    levy_sets: dict[str, LevySet] = {}
    for set_id, item in raw_levies.items():
        _check_grid_id(set_id, origin)
        if set_id in rule_sets:
            raise _collision(set_id)
        levy_sets[set_id] = _parse_levy_set(set_id, item, f"{where}.levy_sets[{set_id}]")
    areas_raw = data.get("areas", [])
    if not isinstance(areas_raw, list):
        raise invalid(f"{where}.areas", areas_raw)
    areas: dict[str, GridArea] = {}
    for index, item in enumerate(areas_raw):
        path = f"{where}.areas[{index}]"
        area = _parse_area(item, path, rule_sets, levy_sets, require_status=origin == CATALOG)
        _check_grid_id(area.id, origin)
        if origin == USER and area.check is not None:  # only the tariff database checks; a copy drops it
            raise EdibertError(
                ErrorCode.CHECK_NOT_IN_USER_FILE,
                f"User grid area '{area.id}' carries a database check; only catalog entries do.",
                tariff_id=area.id,
            )
        if origin == CATALOG and area.db_ref is not None:  # a catalog area is a database entry itself
            raise invalid(f"{path}.db_ref", item.get("db_ref"))
        if area.id in areas:
            raise _collision(area.id)
        areas[area.id] = area
    return GridFeeCatalog(rule_sets, areas, dict.fromkeys(areas, origin), levy_sets)


def merge_grid_fee_catalogs(catalog: GridFeeCatalog | None, user: GridFeeCatalog | None) -> GridFeeCatalog:
    """One view of catalog and user areas; an ID (area or rule set) in both is ``GRID_ID_COLLISION``."""
    rule_sets: dict[str, tuple[Rule, ...]] = {}
    levy_sets: dict[str, LevySet] = {}
    areas: dict[str, GridArea] = {}
    origin: dict[str, str] = {}
    for part in (catalog, user):
        if part is None:
            continue
        for set_id, rules in part.rule_sets.items():
            if set_id in rule_sets:
                raise _collision(set_id)
            rule_sets[set_id] = rules
        for set_id, levies in part.levy_sets.items():
            if set_id in levy_sets or set_id in rule_sets:
                raise _collision(set_id)
            levy_sets[set_id] = levies
        for area_id, area in part.areas.items():
            if area_id in areas:
                raise _collision(area_id)
            areas[area_id] = area
            origin[area_id] = part.origin[area_id]
    return GridFeeCatalog(rule_sets, areas, origin, levy_sets)


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


def put_user_grid_area(
    document: Mapping[str, Any],
    area: Mapping[str, Any],
    *,
    rule_sets: Mapping[str, Any] | None = None,
    levy_sets: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """A copy of a user grid document with ``area`` added or replaced (same ID); the result is validated.

    ``rule_sets`` / ``levy_sets`` are added or replaced by ID next to it (the sets the area names)."""
    result = copy.deepcopy(dict(as_dict(document, "user_grid_fees")))
    area_id = as_dict(area, "user_grid_fees.area").get("id")
    areas = result.get("areas", [])
    if not isinstance(areas, list):
        raise invalid("user_grid_fees.areas", areas)
    kept = [item for item in areas if not (isinstance(item, dict) and item.get("id") == area_id)]
    result["areas"] = [*kept, copy.deepcopy(dict(area))]
    for key, sets in (("rule_sets", rule_sets), ("levy_sets", levy_sets)):
        if sets:
            target = dict(as_dict(result.get(key, {}), f"user_grid_fees.{key}"))
            target.update(copy.deepcopy(dict(sets)))
            result[key] = target
    parse_grid_fee_catalog(result, USER)
    return result


def save_user_grid_area(
    path: Path,
    area: Mapping[str, Any],
    *,
    rule_sets: Mapping[str, Any] | None = None,
    levy_sets: Mapping[str, Any] | None = None,
) -> None:
    """Add or replace one area (and the sets it names) in ``user_grid_fees.json``; other entries stay untouched.

    A missing file is created with the current ``tariff_format``. The whole file is validated before it is
    written, so an invalid area or an unmigrated file leaves the file unchanged.
    """
    document = _read_json(path) if path.exists() else empty_user_grid_document()
    write_json_atomic(path, put_user_grid_area(document, area, rule_sets=rule_sets, levy_sets=levy_sets))


def area_document(document: Mapping[str, Any], area_id: str) -> dict[str, Any]:
    """The raw area ``area_id`` of a grid document with the rules of its rule set and its levy set inlined:
    ``{"area": {...}, "rules": [...], "levies": {...} | None}`` (the input of version and sharing)."""
    data = as_dict(document, "grid_fees")
    for item in data.get("areas") or []:
        if isinstance(item, dict) and item.get("id") == area_id:
            area = dict(item)
            break
    else:
        raise EdibertError(ErrorCode.GRID_AREA_UNKNOWN, f"Unknown grid area '{area_id}'.", area_id=area_id)
    rule_set, levy_set = area.get("rule_set"), area.get("levy_set")
    rule_sets = as_dict(data.get("rule_sets", {}), "grid_fees.rule_sets")
    levy_sets = as_dict(data.get("levy_sets", {}), "grid_fees.levy_sets")
    if rule_set is not None and rule_set not in rule_sets:
        raise invalid(f"grid_fees.areas[{area_id}].rule_set", rule_set)
    if levy_set is not None and levy_set not in levy_sets:
        raise invalid(f"grid_fees.areas[{area_id}].levy_set", levy_set)
    return {
        "area": copy.deepcopy(area),
        "rules": copy.deepcopy(list(rule_sets[rule_set])) if rule_set else [],
        "levies": copy.deepcopy(dict(levy_sets[levy_set])) if levy_set else None,
    }


def user_area_entry(entry: Mapping[str, Any], area_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """An inlined area (``area_document``) as a user area ``area_id`` with its own rule and levy set.

    Returns ``(area, rule_sets, levy_sets)`` for :func:`put_user_grid_area`; the sets are named after the area
    (``<area_id>`` and ``<area_id>_levies``). ``check`` and ``db_ref`` are dropped; the caller sets ``db_ref``.
    """
    if not area_id.startswith(USER_PREFIX):
        raise EdibertError(
            ErrorCode.GRID_ID_PREFIX_MISSING, f"User grid ID '{area_id}' must start with '{USER_PREFIX}'.", grid_id=area_id
        )
    area = {key: value for key, value in copy.deepcopy(dict(entry["area"])).items() if key not in ("check", "db_ref")}
    area["id"] = area_id
    area.pop("rule_set", None)
    area.pop("levy_set", None)
    rule_sets: dict[str, Any] = {}
    levy_sets: dict[str, Any] = {}
    if entry.get("rules"):
        rule_sets[area_id] = copy.deepcopy(list(entry["rules"]))
        area["rule_set"] = area_id
    if entry.get("levies"):
        levy_sets[f"{area_id}_levies"] = copy.deepcopy(dict(entry["levies"]))
        area["levy_set"] = f"{area_id}_levies"
    return area, rule_sets, levy_sets


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

    The base price comes from the area (by metering type) and the area's rule set applies. Capacity
    charges are filtered by ``include_status`` like the rules; a missing ``quarter_hour_meter`` never skips one
    (the operator bills the peak anyway), it only means the house cannot supply the state.
    """
    if config.area_id not in catalog.areas:
        raise EdibertError(
            ErrorCode.GRID_AREA_UNKNOWN, f"Unknown grid area '{config.area_id}'.", area_id=config.area_id
        )
    area = catalog.areas[config.area_id]
    base = area.base_cent_kwh[config.power_metering]
    rules = catalog.rule_sets.get(area.rule_set, ()) if area.rule_set else ()
    active, skipped = _filter_rules(rules, config)
    capacity = tuple(
        charge for charge in area.capacity_charges if charge.status is None or charge.status in config.include_status
    )
    capacity_skipped = {
        charge.id: charge.status
        for charge in area.capacity_charges
        if charge.status is not None and charge.status not in config.include_status
    }
    levies = catalog.levy_sets[area.levy_set] if area.levy_set else None
    components = _resolve_parts(area, area.components + (levies.components if levies else ()), config.power_metering)
    fixed = _resolve_parts(area, area.fixed + (levies.fixed if levies else ()), config.power_metering)
    return GridFee(
        config.area_id,
        float(base),
        tuple(active),
        tuple(skipped),
        capacity=capacity,
        capacity_skipped=capacity_skipped,
        quarter_hour_meter=config.quarter_hour_meter,
        components=components,
        fixed=fixed,
    )


def _resolve_parts(area: GridArea, parts: tuple[GridPart, ...], metering: str) -> tuple[ResolvedPart, ...]:
    """The values for the house's metering type; one that is not modeled (``null``) is an error, never 0."""
    resolved = []
    for part in parts:
        value = part.by_metering[metering]
        if value is None:
            raise EdibertError(
                ErrorCode.GRID_METERING_NOT_MODELED,
                f"Grid area '{area.id}' does not model '{part.id}' for {metering}; enter own values.",
                area_id=area.id,
                item_id=part.id,
                power_metering=metering,
            )
        resolved.append(ResolvedPart(part.id, part.label, value))
    return tuple(resolved)
