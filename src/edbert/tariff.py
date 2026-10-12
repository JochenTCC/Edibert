"""Tariff model: strict parser and the per-slot price evaluation (supplier part)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from edbert._fields import (
    as_dict,
    check_known,
    get_bool,
    get_choice_list,
    get_date,
    get_number,
    get_str,
    invalid,
    missing,
)
from edbert.context import PricingContext
from edbert.errors import EdbertError, ErrorCode
from edbert.rules import (
    REQUIRES,
    Rule,
    apply_effect,
    day_info,
    matching_rule,
    needs_calendar,
    parse_extra_dates,
    parse_holiday_mode,
    parse_rules,
)

if TYPE_CHECKING:
    from edbert.gridfee import GridFee

IMPORT = "import"
EXPORT = "export"

IMPORT_TYPES = ("fixed_cent", "spot_hourly", "ex_post_spot", "monthly_market", "monthly_table")
EXPORT_TYPES = ("fixed", "spot_hourly", "ex_post_spot", "monthly_table")
SPOT_IMPORT_TYPES = ("spot_hourly", "ex_post_spot", "monthly_market")
SPOT_EXPORT_TYPES = ("spot_hourly", "ex_post_spot")

FEE_FIELDS = ("monthly_fee_eur", "grid_monthly_fee_eur", "metering_monthly_fee_eur", "other_monthly_fee_eur")
TARIFF_FIELDS = (
    "id", "label", "type", "land", "currency", "supplier_id", "notes",
    "settlement_fee_cent_kwh", "markup_percent", "prices_include_vat", "vat_percent", "settlement_mtu",
    "fix_cent_kwh", "k_push_cent", "monthly_rates", "monthly_seed",
    "feed_in_fee_factor", "feed_in_fix_cent",
    "rules", "price_floor_cent_kwh", "price_cap_cent_kwh", "requires", "behavior_notes",
    "source", "last_verified", "holidays", "extra_holiday_dates", "individual", "applies_to",
    *FEE_FIELDS,
)  # fmt: skip
UNSUPPORTED_FIELDS = ("tiers", "demand")


@dataclass(frozen=True)
class Tariff:
    id: str
    direction: str
    type: str
    label: str
    supplier_id: str
    land: str | None
    currency: str | None
    settlement_fee_cent_kwh: float
    markup_percent: float
    prices_include_vat: bool
    vat_percent: float
    settlement_mtu: str
    fix_cent_kwh: float | None
    k_push_cent: float | None
    feed_in_fee_factor: float
    feed_in_fix_cent: float
    monthly_rates: Mapping[tuple[int, int], float]
    fees: Mapping[str, float]
    rules: tuple[Rule, ...]
    price_floor_cent_kwh: float | None
    price_cap_cent_kwh: float | None
    requires: tuple[str, ...]
    behavior_notes: str | None
    source: str | None
    last_verified: date | None
    holiday_mode: str
    extra_holiday_dates: frozenset[date]
    individual: bool

    @property
    def needs_calendar(self) -> bool:
        """True if holidays can change a result (weekday filters present, holidays not ignored)."""
        return needs_calendar(self.rules, self.holiday_mode)

    @property
    def is_spot(self) -> bool:
        return self.type in (SPOT_IMPORT_TYPES if self.direction == IMPORT else SPOT_EXPORT_TYPES)

    @property
    def uses_market_price(self) -> bool:
        """True if a slot price needs the market price (spot type or a rule filtering on it)."""
        return self.is_spot or any(rule.uses_market_price for rule in self.rules)


@dataclass(frozen=True)
class PriceResult:
    """Price of one slot with the intermediate steps (cent/kWh)."""

    base_cent: float
    rule_id: str | None
    after_rule_cent: float
    after_limits_cent: float  # supplier part after rules and floor/cap, before grid fee and VAT
    cent: float  # final, rounded to 4 decimals: (supplier part + grid fee) incl. VAT
    grid_cent: float = 0.0
    grid_rule_id: str | None = None


def _parse_monthly_rates(raw: object, path: str) -> dict[tuple[int, int], float]:
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise invalid(path, raw)
    table: dict[tuple[int, int], float] = {}
    for index, row in enumerate(raw):
        where = f"{path}[{index}]"
        data = as_dict(row, where)
        check_known(data, ("year", "month", "tariff_cent_kwh"), where)
        year, month = data.get("year"), data.get("month")
        if isinstance(year, bool) or not isinstance(year, int):
            raise invalid(f"{where}.year", year)
        if isinstance(month, bool) or not isinstance(month, int) or not 1 <= month <= 12:
            raise invalid(f"{where}.month", month)
        value = get_number(data, "tariff_cent_kwh", where, required=True)
        assert value is not None
        table[(year, month)] = value
    return table


def _reject_unsupported(raw: Mapping[str, Any], tariff_id: str) -> None:
    for name in UNSUPPORTED_FIELDS:
        if name in raw:
            raise EdbertError(
                ErrorCode.UNSUPPORTED_FEATURE,
                f"Unsupported feature '{name}' in tariff '{tariff_id}'.",
                feature=name,
                tariff_id=tariff_id,
            )
    if raw.get("applies_to", "main") != "main":
        raise EdbertError(
            ErrorCode.UNSUPPORTED_FEATURE,
            f"Unsupported feature 'applies_to' in tariff '{tariff_id}'.",
            feature="applies_to",
            tariff_id=tariff_id,
        )


def _require_type_fields(raw: Mapping[str, Any], tariff_type: str, tariff_id: str) -> None:
    needed = {"fixed_cent": "fix_cent_kwh", "fixed": "k_push_cent", "monthly_table": "monthly_rates"}
    key = needed.get(tariff_type)
    if key and raw.get(key) in (None, []):
        raise missing(f"{tariff_id}.{key}")


def parse_tariff(raw: object, direction: str) -> Tariff:
    """Validate one tariff entry strictly. Unknown or unsupported fields are errors."""
    if direction not in (IMPORT, EXPORT):
        raise invalid("direction", direction)
    probe = as_dict(raw, direction)
    tariff_id = get_str(probe, "id", direction, required=True)
    assert tariff_id is not None
    _reject_unsupported(probe, tariff_id)
    check_known(probe, TARIFF_FIELDS, tariff_id)
    tariff_type = get_str(probe, "type", tariff_id, required=True)
    if tariff_type not in (IMPORT_TYPES if direction == IMPORT else EXPORT_TYPES):
        raise invalid(f"{tariff_id}.type", tariff_type)
    _require_type_fields(probe, tariff_type, tariff_id)
    return _build(probe, direction, tariff_type, tariff_id)


def _build(raw: Mapping[str, Any], direction: str, tariff_type: str, tid: str) -> Tariff:
    floor = get_number(raw, "price_floor_cent_kwh", tid)
    cap = get_number(raw, "price_cap_cent_kwh", tid)
    if floor is not None and cap is not None and floor > cap:
        raise invalid(f"{tid}.price_cap_cent_kwh", cap)
    mtu = get_str(raw, "settlement_mtu", tid) or "15min"
    if mtu not in ("15min", "60min"):
        raise invalid(f"{tid}.settlement_mtu", mtu)
    return Tariff(
        id=tid,
        direction=direction,
        type=tariff_type,
        label=get_str(raw, "label", tid) or tid,
        supplier_id=get_str(raw, "supplier_id", tid, required=True) or tid,
        land=get_str(raw, "land", tid),
        currency=get_str(raw, "currency", tid),
        settlement_fee_cent_kwh=get_number(raw, "settlement_fee_cent_kwh", tid) or 0.0,
        markup_percent=get_number(raw, "markup_percent", tid) or 0.0,
        prices_include_vat=get_bool(raw, "prices_include_vat", tid, True),
        vat_percent=get_number(raw, "vat_percent", tid, minimum=0) or 0.0,
        settlement_mtu=mtu,
        fix_cent_kwh=get_number(raw, "fix_cent_kwh", tid),
        k_push_cent=get_number(raw, "k_push_cent", tid),
        feed_in_fee_factor=get_number(raw, "feed_in_fee_factor", tid, minimum=0) or 0.0,
        feed_in_fix_cent=get_number(raw, "feed_in_fix_cent", tid) or 0.0,
        monthly_rates=_parse_monthly_rates(raw.get("monthly_rates"), f"{tid}.monthly_rates"),
        fees={key: get_number(raw, key, tid, minimum=0) or 0.0 for key in FEE_FIELDS if key in raw},
        rules=parse_rules(raw.get("rules"), tid),
        price_floor_cent_kwh=floor,
        price_cap_cent_kwh=cap,
        requires=get_choice_list(raw, "requires", tid, REQUIRES),
        behavior_notes=get_str(raw, "behavior_notes", tid),
        source=get_str(raw, "source", tid),
        last_verified=get_date(raw, "last_verified", tid),
        holiday_mode=parse_holiday_mode(raw.get("holidays"), f"{tid}.holidays"),
        extra_holiday_dates=parse_extra_dates(raw.get("extra_holiday_dates"), f"{tid}.extra_holiday_dates"),
        individual=get_bool(raw, "individual", tid, False),
    )


def _base_cent(tariff: Tariff, local: datetime, epex_cent: float | None) -> float:
    slot = local.isoformat()
    spot = SPOT_IMPORT_TYPES if tariff.direction == IMPORT else SPOT_EXPORT_TYPES
    if tariff.type in spot:
        if epex_cent is None:
            raise EdbertError(
                ErrorCode.MARKET_PRICE_REQUIRED,
                f"Tariff '{tariff.id}' needs a market price for slot {slot}.",
                slot=slot,
                tariff_id=tariff.id,
            )
        if tariff.direction == IMPORT:
            return epex_cent * (1.0 + tariff.markup_percent / 100.0) + tariff.settlement_fee_cent_kwh
        return (
            epex_cent
            - tariff.feed_in_fee_factor * abs(epex_cent)
            - tariff.settlement_fee_cent_kwh
            + tariff.feed_in_fix_cent
        )
    if tariff.type == "monthly_table":
        rate = tariff.monthly_rates.get((local.year, local.month))
        if rate is None:
            raise EdbertError(
                ErrorCode.PRICE_MISSING,
                f"No monthly rate for {local.year}-{local.month:02d} in tariff '{tariff.id}'.",
                slot=slot,
                tariff_id=tariff.id,
            )
        return rate
    fixed = tariff.fix_cent_kwh if tariff.direction == IMPORT else tariff.k_push_cent
    assert fixed is not None  # guaranteed by parse_tariff
    return fixed


def _clamp(value: float, tariff: Tariff) -> float:
    if tariff.price_floor_cent_kwh is not None:
        value = max(value, tariff.price_floor_cent_kwh)
    if tariff.price_cap_cent_kwh is not None:
        value = min(value, tariff.price_cap_cent_kwh)
    return value


def evaluate(
    tariff: Tariff,
    slot_start: datetime,
    ctx: PricingContext,
    epex_cent: float | None = None,
    grid_fee: GridFee | None = None,
) -> PriceResult:
    """Price (cent/kWh) of the slot starting at ``slot_start``, with intermediate steps.

    Order: base price, first matching rule, floor/cap, grid fee (import only, optional), VAT.
    """
    local = ctx.to_local(slot_start)
    base = _base_cent(tariff, local, epex_cent)
    rule = matching_rule(
        tariff.rules,
        local,
        day_info(tariff.rules, tariff.holiday_mode, tariff.extra_holiday_dates, local, ctx),
        holiday_mode=tariff.holiday_mode,
        epex_cent=epex_cent,
        tariff_id=tariff.id,
    )
    after_rule = apply_effect(base, rule.effect, rule.id) if rule else base
    limited = _clamp(after_rule, tariff)
    grid_cent, grid_rule = (0.0, None)
    if grid_fee is not None and tariff.direction == IMPORT:
        grid_cent, grid_rule = grid_fee.work_cent(local, ctx)
    net = limited + grid_cent
    gross = net if tariff.prices_include_vat else net * (1.0 + tariff.vat_percent / 100.0)
    return PriceResult(
        base, rule.id if rule else None, after_rule, limited, round(gross, 4), grid_cent, grid_rule
    )


def price_cent(
    tariff: Tariff,
    slot_start: datetime,
    ctx: PricingContext,
    epex_cent: float | None = None,
    grid_fee: GridFee | None = None,
) -> float:
    """Final price in cent/kWh for one slot."""
    return evaluate(tariff, slot_start, ctx, epex_cent, grid_fee).cent
