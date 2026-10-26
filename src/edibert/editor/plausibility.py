"""Plausibility checks for the editor: rules that never apply, rules hidden behind others, odd prices."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from edibert.context import PricingContext
from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.rules import DayInfo, Rule, date_matches, day_info, window_slots
from edibert.tariff import EXPORT, IMPORT, Tariff

IMPORT_PRICE_RANGE = (5.0, 60.0)  # cent/kWh, typical household work price incl. everything
EXPORT_PRICE_MAX = 30.0
RULE_PRICE_MAX = 80.0


@dataclass
class RuleStats:
    """How often a rule could apply (``candidates``) and how often it is the first match (``wins``)."""

    candidates: int = 0
    wins: int = 0
    lost_to: Counter[str] = field(default_factory=Counter)


def _day(tariff: Tariff, ctx: PricingContext, when: date) -> DayInfo:
    local = ctx.to_local(datetime(when.year, when.month, when.day, 12, 0))
    try:
        return day_info(tariff.rules, tariff.holiday_mode, tariff.extra_holiday_dates, local, ctx)
    except EdibertError as err:
        if err.code in (ErrorCode.HOLIDAY_REGION_MISSING, ErrorCode.HOLIDAY_REGION_UNKNOWN):
            return DayInfo(when.weekday(), False)  # no calendar: the analysis ignores holidays
        raise


def analyze_rules(tariff: Tariff, ctx: PricingContext, year: int) -> dict[str, RuleStats]:
    """Walk through the calendar years ``year`` and ``year + 1`` and count wins per rule."""
    stats = {rule.id: RuleStats() for rule in tariff.rules}
    windows: dict[str, frozenset[int]] = {rule.id: window_slots(rule) for rule in tariff.rules}
    day = date(year, 1, 1)
    while day.year < year + 2:
        info = _day(tariff, ctx, day)
        owner: dict[int, str] = {}
        for rule in tariff.rules:
            if not date_matches(rule, day, info, tariff.holiday_mode):
                continue
            slots = windows[rule.id]
            stats[rule.id].candidates += len(slots)
            for index in sorted(slots):
                if index in owner:
                    stats[rule.id].lost_to[owner[index]] += 1
                else:
                    owner[index] = rule.id
                    stats[rule.id].wins += 1
        day += timedelta(days=1)
    return stats


def _rule_warnings(tariff: Tariff, stats: dict[str, RuleStats]) -> list[EdibertWarning]:
    found: list[EdibertWarning] = []
    for rule in tariff.rules:
        entry = stats[rule.id]
        if entry.candidates == 0:
            found.append(
                EdibertWarning(WarningCode.RULE_NEVER_APPLIES, f"Rule '{rule.id}' never applies.", {"rule_id": rule.id})
            )
        elif entry.wins == 0:
            by = entry.lost_to.most_common(1)[0][0]
            found.append(
                EdibertWarning(
                    WarningCode.RULE_SHADOWED,
                    f"Rule '{rule.id}' is hidden behind rule '{by}'.",
                    {"rule_id": rule.id, "by": by},
                )
            )
    return found


def _value_of(tariff: Tariff) -> float | None:
    return tariff.fix_cent_kwh if tariff.direction == IMPORT else tariff.k_push_cent


def _price_warnings(tariff: Tariff) -> list[EdibertWarning]:
    found: list[EdibertWarning] = []
    value = _value_of(tariff)
    if value is not None and tariff.type in ("fixed_cent", "fixed"):
        low, high = IMPORT_PRICE_RANGE if tariff.direction == IMPORT else (0.0, EXPORT_PRICE_MAX)
        if not low <= value <= high:
            found.append(EdibertWarning(WarningCode.PRICE_UNUSUAL, f"Unusual price {value}.", {"value": value}))
    for rule in tariff.rules:
        if rule.effect.mode == "absolute_cent" and rule.effect.value is not None and rule.effect.value > RULE_PRICE_MAX:
            found.append(
                EdibertWarning(WarningCode.RULE_PRICE_UNUSUAL, f"Unusual rule price {rule.effect.value}.", {"rule_id": rule.id, "value": rule.effect.value})
            )
    if tariff.is_spot and tariff.direction == IMPORT and tariff.prices_include_vat:
        found.append(EdibertWarning(WarningCode.SPOT_PRICES_GROSS, "Spot prices are usually net.", {"tariff_id": tariff.id}))
    return found


def plausibility_warnings(tariff: Tariff, ctx: PricingContext, year: int) -> list[EdibertWarning]:
    """All plausibility findings for a tariff (rules and prices)."""
    stats = analyze_rules(tariff, ctx, year) if tariff.rules else {}
    return _rule_warnings(tariff, stats) + _price_warnings(tariff)


def rule_by_id(tariff: Tariff, rule_id: str) -> Rule:
    return next(rule for rule in tariff.rules if rule.id == rule_id)


__all__ = ["EXPORT", "RuleStats", "analyze_rules", "plausibility_warnings", "rule_by_id"]
