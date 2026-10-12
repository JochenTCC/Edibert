"""Time rules: parsing, matching and effects. First matching rule wins (see the spec)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from edbert._fields import (
    as_dict,
    check_known,
    get_choice_list,
    get_date,
    get_number,
    get_str,
    invalid,
    missing,
    parse_date,
)
from edbert.context import PricingContext
from edbert.errors import EdbertError, ErrorCode

MODE_ABSOLUTE = "absolute_cent"
MODE_ADD = "add_cent"
MODE_PERCENT_OFF = "percent_off"
MODES = (MODE_ABSOLUTE, MODE_ADD, MODE_PERCENT_OFF)

REQUIRES = ("smart_meter", "quarter_hour_meter", "separate_meter", "controllable_device")
HOLIDAY = "holiday"

RULE_FIELDS = (
    "id", "label", "valid_from", "valid_to", "months", "weekdays", "time",
    "effect", "when_market_cent_kwh", "requires",
)  # fmt: skip
GRID_RULE_FIELDS = (
    *(name for name in RULE_FIELDS if name != "when_market_cent_kwh"), "status", "source", "note",
)  # fmt: skip
HOLIDAY_MODES = ("sunday", "weekday", "own")
STATUSES = ("verordnet", "entwurf", "illustrativ")

_DAY_NAMES = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
_DAY_GROUPS = {"weekday": {0, 1, 2, 3, 4}, "weekend": {5, 6}}
_MINUTES_PER_DAY = 24 * 60
_HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class Effect:
    mode: str
    value: float | None  # None only in grid-fee catalog rules whose value is not known yet


@dataclass(frozen=True)
class DayInfo:
    """What the weekday filters see for one local date."""

    weekday: int  # effective weekday (holiday counts as Sunday in "sunday" mode)
    is_holiday: bool


@dataclass(frozen=True)
class Rule:
    id: str
    label: str
    valid_from: date | None
    valid_to: date | None
    months: frozenset[int] | None
    weekdays: frozenset[int | str] | None  # ints 0..6 and/or the token "holiday"
    from_min: int
    to_min: int
    effect: Effect
    market_below: float | None
    market_above: float | None
    requires: tuple[str, ...]
    status: str | None = None  # grid-fee rules only
    source: str | None = None
    note: str | None = None

    @property
    def has_holiday_token(self) -> bool:
        return self.weekdays is not None and HOLIDAY in self.weekdays

    @property
    def uses_market_price(self) -> bool:
        return self.market_below is not None or self.market_above is not None


def _parse_hhmm(raw: object, path: str, *, allow_24: bool = False) -> int:
    match = _HHMM.match(raw) if isinstance(raw, str) else None
    if match is None:
        raise invalid(path, raw)
    hour, minute = int(match.group(1)), int(match.group(2))
    if minute > 59 or hour > 24 or (hour == 24 and (minute or not allow_24)):
        raise invalid(path, raw)
    return hour * 60 + minute


def _parse_time(raw: object, path: str) -> tuple[int, int]:
    if raw is None:
        return 0, _MINUTES_PER_DAY
    data = as_dict(raw, path)
    check_known(data, ("from", "to"), path)
    start = _parse_hhmm(data.get("from"), f"{path}.from")
    end = _parse_hhmm(data.get("to"), f"{path}.to", allow_24=True)
    if start == end:
        raise invalid(path, raw)
    return start, end


def _parse_months(raw: object, path: str) -> frozenset[int] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw:
        raise invalid(path, raw)
    for month in raw:
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise invalid(path, month)
    return frozenset(raw)


def _weekday_tokens(item: object, path: str) -> set[int | str]:
    if isinstance(item, bool):
        raise invalid(path, item)
    if isinstance(item, int) and 0 <= item <= 6:
        return {item}
    if isinstance(item, str):
        word = item.strip().lower()
        if word in _DAY_NAMES:
            return {_DAY_NAMES[word]}
        if word in _DAY_GROUPS:
            return set(_DAY_GROUPS[word])
        if word == HOLIDAY:
            return {HOLIDAY}
    raise invalid(path, item)


def _parse_weekdays(raw: object, path: str) -> frozenset[int | str] | None:
    if raw is None:
        return None
    items = [raw] if isinstance(raw, str) else raw
    if not isinstance(items, list) or not items:
        raise invalid(path, raw)
    tokens: set[int | str] = set()
    for item in items:
        tokens |= _weekday_tokens(item, path)
    return frozenset(tokens)


def _parse_effect(raw: object, path: str, *, allow_null: bool = False) -> Effect:
    if raw is None:
        raise missing(path)
    data = as_dict(raw, path)
    check_known(data, ("mode", "value"), path)
    mode = data.get("mode")
    if mode not in MODES:
        raise invalid(f"{path}.mode", mode)
    value = get_number(data, "value", path, required=not allow_null)
    if value is not None and (
        (mode == MODE_ABSOLUTE and value < 0) or (mode == MODE_PERCENT_OFF and not 0 <= value <= 100)
    ):
        raise invalid(f"{path}.value", value)
    return Effect(mode, value)


def _parse_market(raw: object, path: str) -> tuple[float | None, float | None]:
    if raw is None:
        return None, None
    data = as_dict(raw, path)
    check_known(data, ("below", "above"), path)
    if len(data) != 1:
        raise invalid(path, raw)
    below = get_number(data, "below", path)
    above = get_number(data, "above", path)
    return below, above


def _parse_status(data: Mapping[str, Any], path: str) -> str | None:
    status = get_str(data, "status", path)
    if status is not None and status not in STATUSES:
        raise invalid(f"{path}.status", status)
    return status


def parse_rule(raw: object, owner_id: str, index: int, *, grid: bool = False) -> Rule:
    """Validate one rule. Unknown fields and bad values are coded errors.

    ``grid=True`` is for grid-fee rules: optional ``status``/``source``/``note`` and an effect
    whose value may still be unknown (``null``).
    """
    path = f"{owner_id}.rules[{index}]"
    data = as_dict(raw, path)
    rule_id = get_str(data, "id", path, required=True)
    assert rule_id is not None
    allowed = GRID_RULE_FIELDS if grid else RULE_FIELDS
    check_known(data, allowed, path, ErrorCode.RULE_UNKNOWN_FIELD, rule_id=rule_id)
    path = f"{owner_id}.rules[{rule_id}]"
    start, end = _parse_time(data.get("time"), f"{path}.time")
    valid_from, valid_to = get_date(data, "valid_from", path), get_date(data, "valid_to", path)
    if valid_from and valid_to and valid_to < valid_from:
        raise invalid(f"{path}.valid_to", data.get("valid_to"))
    below, above = _parse_market(data.get("when_market_cent_kwh"), f"{path}.when_market_cent_kwh")
    return Rule(
        id=rule_id,
        label=get_str(data, "label", path) or rule_id,
        valid_from=valid_from,
        valid_to=valid_to,
        months=_parse_months(data.get("months"), f"{path}.months"),
        weekdays=_parse_weekdays(data.get("weekdays"), f"{path}.weekdays"),
        from_min=start,
        to_min=end,
        effect=_parse_effect(data.get("effect"), f"{path}.effect", allow_null=grid),
        market_below=below,
        market_above=above,
        requires=get_choice_list(data, "requires", path, REQUIRES),
        status=_parse_status(data, path) if grid else None,
        source=get_str(data, "source", path) if grid else None,
        note=get_str(data, "note", path) if grid else None,
    )


def parse_rules(raw: object, owner_id: str, *, grid: bool = False) -> tuple[Rule, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise invalid(f"{owner_id}.rules", raw)
    rules = tuple(parse_rule(item, owner_id, index, grid=grid) for index, item in enumerate(raw))
    ids = [rule.id for rule in rules]
    for rule_id in ids:
        if ids.count(rule_id) > 1:
            raise invalid(f"{owner_id}.rules[{rule_id}].id", rule_id)
    return rules


def _weekday_matches(rule: Rule, day: DayInfo, holiday_mode: str) -> bool:
    if rule.weekdays is None:
        return True
    if day.is_holiday and holiday_mode == "own" and not rule.has_holiday_token:
        return False
    return day.weekday in rule.weekdays or (day.is_holiday and HOLIDAY in rule.weekdays)


def _time_matches(rule: Rule, local: datetime) -> bool:
    minute = local.hour * 60 + local.minute
    if rule.from_min < rule.to_min:
        return rule.from_min <= minute < rule.to_min
    return minute >= rule.from_min or minute < rule.to_min


def _market_matches(rule: Rule, epex_cent: float | None, slot: str, tariff_id: str) -> bool:
    if not rule.uses_market_price:
        return True
    if epex_cent is None:
        raise EdbertError(
            ErrorCode.MARKET_PRICE_REQUIRED,
            f"Rule '{rule.id}' of tariff '{tariff_id}' needs a market price for slot {slot}.",
            slot=slot,
            tariff_id=tariff_id,
        )
    if rule.market_below is not None and epex_cent >= rule.market_below:
        return False
    return not (rule.market_above is not None and epex_cent <= rule.market_above)


def date_matches(rule: Rule, when: date, day: DayInfo, holiday_mode: str) -> bool:
    """True if the rule applies on this date (validity, month and weekday filters; time of day not checked)."""
    if (rule.valid_from and when < rule.valid_from) or (rule.valid_to and when > rule.valid_to):
        return False
    if rule.months is not None and when.month not in rule.months:
        return False
    return _weekday_matches(rule, day, holiday_mode)


def window_slots(rule: Rule) -> frozenset[int]:
    """Indexes (0..95) of the 15-minute slots of a day that lie inside the rule's time window."""
    return frozenset(
        index
        for index in range(96)
        if _time_matches(rule, datetime(2000, 1, 1, index * 15 // 60, index * 15 % 60))
    )


def rule_matches(
    rule: Rule,
    local: datetime,
    day: DayInfo,
    *,
    holiday_mode: str,
    epex_cent: float | None,
    tariff_id: str,
) -> bool:
    """True if ``rule`` applies to the slot starting at ``local`` (local time)."""
    return (
        date_matches(rule, local.date(), day, holiday_mode)
        and _time_matches(rule, local)
        and _market_matches(rule, epex_cent, local.isoformat(), tariff_id)
    )


def matching_rule(
    rules: tuple[Rule, ...],
    local: datetime,
    day: DayInfo,
    *,
    holiday_mode: str,
    epex_cent: float | None,
    tariff_id: str,
) -> Rule | None:
    """First matching rule or ``None``."""
    for rule in rules:
        if rule_matches(
            rule, local, day, holiday_mode=holiday_mode, epex_cent=epex_cent, tariff_id=tariff_id
        ):
            return rule
    return None


def apply_effect(base_cent: float, effect: Effect, rule_id: str = "?") -> float:
    if effect.value is None:
        raise EdbertError(
            ErrorCode.RULE_VALUE_MISSING, f"Rule '{rule_id}' has no value (effect.value is null).", rule_id=rule_id
        )
    if effect.mode == MODE_ABSOLUTE:
        return effect.value
    if effect.mode == MODE_ADD:
        return base_cent + effect.value
    return base_cent * (1.0 - effect.value / 100.0)


def unmet_requirements(requires: tuple[str, ...], capabilities: Mapping[str, Any] | set[str]) -> list[str]:
    """Requirements not in ``capabilities`` (a warning for the caller, never an error here)."""
    return [item for item in requires if item not in capabilities]


def needs_calendar(rules: tuple[Rule, ...], holiday_mode: str) -> bool:
    """True if holidays can change a result: a weekday filter with holidays not ignored, or a holiday token."""
    filtered = [rule for rule in rules if rule.weekdays is not None]
    if any(rule.has_holiday_token for rule in filtered):
        return True
    return bool(filtered) and holiday_mode != "weekday"


def day_info(
    rules: tuple[Rule, ...],
    holiday_mode: str,
    extra_dates: frozenset[date],
    local: datetime,
    ctx: PricingContext,
) -> DayInfo:
    """Weekday and holiday flag for ``local``; the calendar is only built when it can matter."""
    weekday = local.weekday()
    if not needs_calendar(rules, holiday_mode):
        return DayInfo(weekday, False)
    is_holiday = ctx.calendar_for(extra_dates).is_holiday(local.date())
    if is_holiday and holiday_mode == "sunday":
        weekday = 6
    return DayInfo(weekday, is_holiday)


def parse_holiday_mode(raw: object, path: str) -> str:
    """``{"treat_as": "sunday" | "weekday" | "own"}``; default ``sunday``."""
    if raw is None:
        return "sunday"
    data = as_dict(raw, path)
    check_known(data, ("treat_as",), path)
    mode = data.get("treat_as", "sunday")
    if mode not in HOLIDAY_MODES:
        raise invalid(f"{path}.treat_as", mode)
    return mode


def parse_extra_dates(raw: object, path: str) -> frozenset[date]:
    if raw is None:
        return frozenset()
    if not isinstance(raw, list):
        raise invalid(path, raw)
    return frozenset(parse_date(item, path) for item in raw)
