"""Grid fee (Netznutzungsentgelt) work price: house-profile config, optional catalog, evaluation.

The shape follows the Earnie ``netznutzung`` profile field and ``grid_fees.json`` catalog so that
both can be priced identically. Own rules (no catalog area) are new: they model for example the
three levels of section 14a EnWG module 3. Prices are net, cent/kWh.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from edbert._fields import (
    as_dict,
    check_known,
    get_bool,
    get_number,
    get_str,
    invalid,
    missing,
)
from edbert.context import PricingContext
from edbert.errors import EdbertError, ErrorCode
from edbert.rules import (
    STATUSES,
    Rule,
    apply_effect,
    day_info,
    matching_rule,
    parse_extra_dates,
    parse_holiday_mode,
    parse_rules,
)

METERING = ("unmetered_power", "metered_power")
DEFAULT_INCLUDE_STATUS = ("verordnet",)
SKIP_STATUS = "status"
SKIP_NO_QUARTER_HOUR_METER = "no_quarter_hour_meter"

CONFIG_FIELDS = (
    "area_id", "power_metering", "quarter_hour_meter", "base_cent_kwh", "include_status",
    "rules", "holidays", "extra_holiday_dates",
)  # fmt: skip


@dataclass(frozen=True)
class GridFeeConfig:
    """The ``netznutzung`` field of a house profile."""

    area_id: str | None
    power_metering: str
    quarter_hour_meter: bool
    base_cent_kwh: float
    include_status: tuple[str, ...]
    rules: tuple[Rule, ...]
    holiday_mode: str
    extra_holiday_dates: frozenset[date]


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
    rule_sets: Mapping[str, tuple[Rule, ...]]
    areas: Mapping[str, GridArea]


@dataclass(frozen=True)
class SkippedRule:
    rule_id: str
    reason: str  # SKIP_STATUS or SKIP_NO_QUARTER_HOUR_METER
    detail: str | None = None


@dataclass(frozen=True)
class GridFee:
    """A resolved grid fee: base work price plus the rules that are in effect."""

    area_id: str | None
    base_cent_kwh: float
    rules: tuple[Rule, ...]
    skipped: tuple[SkippedRule, ...]
    holiday_mode: str
    extra_holiday_dates: frozenset[date]

    def work_cent(self, local: datetime, ctx: PricingContext) -> tuple[float, str | None]:
        """Net work price and the id of the rule that applied for the slot at ``local``."""
        if not self.rules:
            return self.base_cent_kwh, None
        day = day_info(self.rules, self.holiday_mode, self.extra_holiday_dates, local, ctx)
        rule = matching_rule(
            self.rules, local, day, holiday_mode=self.holiday_mode, epex_cent=None, tariff_id="netznutzung"
        )
        if rule is None:
            return self.base_cent_kwh, None
        return apply_effect(self.base_cent_kwh, rule.effect, rule.id), rule.id


def parse_grid_fee_config(raw: object, label: str = "netznutzung") -> GridFeeConfig:
    """Validate the house-profile field strictly (own rules only without a catalog area)."""
    if raw is None:
        raw = {}
    data = as_dict(raw, label)
    check_known(data, CONFIG_FIELDS, label)
    area_id = get_str(data, "area_id", label)
    metering = get_str(data, "power_metering", label) or METERING[0]
    if metering not in METERING:
        raise invalid(f"{label}.power_metering", metering)
    include = data.get("include_status", list(DEFAULT_INCLUDE_STATUS))
    if not isinstance(include, list) or any(item not in STATUSES for item in include):
        raise invalid(f"{label}.include_status", include)
    rules = parse_rules(data.get("rules"), label, grid=True)
    if area_id is not None and rules:
        raise invalid(f"{label}.rules", "rules are only allowed without area_id")
    return GridFeeConfig(
        area_id=area_id,
        power_metering=metering,
        quarter_hour_meter=get_bool(data, "quarter_hour_meter", label, False),
        base_cent_kwh=get_number(data, "base_cent_kwh", label, minimum=0) or 0.0,
        include_status=tuple(include),
        rules=rules,
        holiday_mode=parse_holiday_mode(data.get("holidays"), f"{label}.holidays"),
        extra_holiday_dates=parse_extra_dates(data.get("extra_holiday_dates"), f"{label}.extra_holiday_dates"),
    )


def _parse_area(raw: object, index: int, rule_sets: Mapping[str, tuple[Rule, ...]]) -> GridArea:
    where = f"grid_fees.areas[{index}]"
    data = as_dict(raw, where)
    area_id = get_str(data, "id", where, required=True)
    assert area_id is not None
    check_known(data, ("id", "label", "land", "base_cent_kwh", "rule_set", "source"), where)
    raw_base = data.get("base_cent_kwh")
    if raw_base is None:
        raise missing(f"{where}.base_cent_kwh")
    base = as_dict(raw_base, f"{where}.base_cent_kwh")
    check_known(base, METERING, f"{where}.base_cent_kwh")
    prices ={key: get_number(base, key, f"{where}.base_cent_kwh", required=True, minimum=0) for key in METERING}
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


def parse_grid_fee_catalog(doc: object) -> GridFeeCatalog:
    """Validate a ``grid_fees.json`` document (Earnie shape: ``rule_sets`` and ``areas``)."""
    data = as_dict(doc, "grid_fees")
    check_known(data, ("description", "rule_sets", "areas"), "grid_fees")
    raw_sets = as_dict(data.get("rule_sets", {}), "grid_fees.rule_sets")
    rule_sets: dict[str, tuple[Rule, ...]] = {}
    for set_id, items in raw_sets.items():
        rules = parse_rules(items, f"grid_fees.rule_sets[{set_id}]", grid=True)
        for rule in rules:
            if rule.status is None:
                raise missing(f"grid_fees.rule_sets[{set_id}].rules[{rule.id}].status")
        rule_sets[set_id] = rules
    areas_raw = data.get("areas", [])
    if not isinstance(areas_raw, list):
        raise invalid("grid_fees.areas", areas_raw)
    areas: dict[str, GridArea] = {}
    for index, item in enumerate(areas_raw):
        area = _parse_area(item, index, rule_sets)
        if area.id in areas:
            raise invalid(f"grid_fees.areas[{area.id}].id", area.id)
        areas[area.id] = area
    return GridFeeCatalog(rule_sets, areas)


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        return as_dict(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, ValueError) as exc:
        raise EdbertError(ErrorCode.FILE_INVALID, f"Cannot read file '{path}': {exc}", path=str(path)) from exc


def load_grid_fee_catalog(path: Path) -> GridFeeCatalog:
    return parse_grid_fee_catalog(_read_json(path))


def load_grid_fee_config(path: Path) -> GridFeeConfig:
    """Config from a file: either the bare object or a document with a ``netznutzung`` key."""
    doc = _read_json(path)
    return parse_grid_fee_config(doc.get("netznutzung", doc))


def _filter_rules(rules: tuple[Rule, ...], config: GridFeeConfig) -> tuple[list[Rule], list[SkippedRule]]:
    active: list[Rule] = []
    skipped: list[SkippedRule] = []
    for rule in rules:
        if rule.status is not None and rule.status not in config.include_status:
            skipped.append(SkippedRule(rule.id, SKIP_STATUS, rule.status))
        elif "quarter_hour_meter" in rule.requires and not config.quarter_hour_meter:
            skipped.append(SkippedRule(rule.id, SKIP_NO_QUARTER_HOUR_METER))
        elif rule.effect.value is None:
            raise EdbertError(
                ErrorCode.RULE_VALUE_MISSING, f"Included rule '{rule.id}' has no value.", rule_id=rule.id
            )
        else:
            active.append(rule)
    return active, skipped


def resolve_grid_fee(config: GridFeeConfig, catalog: GridFeeCatalog | None = None) -> GridFee:
    """Combine the profile field and the catalog into an evaluable grid fee.

    With a catalog area the base price comes from the catalog (by metering type) and the area's
    rule set applies; without an area the profile's own base price and own rules apply.
    """
    if config.area_id is None:
        base, rules = config.base_cent_kwh, config.rules
    else:
        if catalog is None or config.area_id not in catalog.areas:
            raise EdbertError(
                ErrorCode.GRID_AREA_UNKNOWN, f"Unknown grid area '{config.area_id}'.", area_id=config.area_id
            )
        area = catalog.areas[config.area_id]
        base = area.base_cent_kwh[config.power_metering]
        rules = catalog.rule_sets.get(area.rule_set, ()) if area.rule_set else ()
    active, skipped = _filter_rules(rules, config)
    return GridFee(
        config.area_id, float(base), tuple(active), tuple(skipped), config.holiday_mode, config.extra_holiday_dates
    )
