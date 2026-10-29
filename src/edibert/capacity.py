"""Capacity charge (Leistungspreis): monthly grid fee on the highest quarter-hour import power (section 5b).

A grid area may carry ``capacity_charges``: a list of entries with a minimum assessed power and power bands
priced in cent per kW and month (SNE-G-V, Austria from 2027). The charge depends on the month-to-date peak,
so it is never folded into a slot price. Edibert is stateless: the peak so far comes from the caller on every
call and is never stored, guessed or taken as ``0``.
"""

from __future__ import annotations

import calendar
import itertools
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from edibert._fields import (
    as_dict,
    check_known,
    get_date,
    get_number,
    get_str,
    invalid,
    missing,
)
from edibert.context import PricingContext
from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.rules import STATUSES

BASIS_MONTHLY_PEAK_15MIN = "monthly_peak_15min"
BASES = (BASIS_MONTHLY_PEAK_15MIN,)
UNIT = "EUR once per month, net"
CHARGE_FIELDS = (
    "id", "label", "basis", "min_kw", "bands", "valid_from", "valid_to", "status", "source", "note",
)  # fmt: skip
BAND_FIELDS = ("up_to_kw", "cent_per_kw_month")
_EUR_DECIMALS = 2  # invoice amounts, rounded commercially (SNE-G-V section 28 (2))
_LADDER_DECIMALS = 4


@dataclass(frozen=True)
class CapacityBand:
    """The rate applies to the share of the peak below ``up_to_kw`` (``None``: no upper limit)."""

    up_to_kw: float | None
    cent_per_kw_month: float


@dataclass(frozen=True)
class CapacityCharge:
    id: str
    label: str
    basis: str
    min_kw: float
    bands: tuple[CapacityBand, ...]
    valid_from: date | None
    valid_to: date | None
    status: str | None
    source: str
    note: str

    def covers(self, month: date) -> bool:
        first, last = month_bounds(month)
        return (self.valid_from is None or self.valid_from <= first) and (self.valid_to is None or last <= self.valid_to)

    @property
    def convex(self) -> bool:
        rates = [band.cent_per_kw_month for band in self.bands]
        return all(low <= high for low, high in itertools.pairwise(rates))


@dataclass(frozen=True)
class CapacityState:
    """Measured month-to-date peak: highest clock-aligned 15-minute average import power (kW) up to ``as_of``."""

    peak_15min_kw: float
    as_of: datetime

    def to_dict(self) -> dict[str, Any]:
        return {"peak_15min_kw": self.peak_15min_kw, "as_of": self.as_of.isoformat()}


@dataclass(frozen=True)
class LadderRung:
    """Cost of a month peak of ``up_to_kw``; ``marginal_eur_per_kw`` is the slope above this point."""

    up_to_kw: float
    extra_eur: float
    marginal_eur_per_kw: float
    reached: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "up_to_kw": self.up_to_kw,
            "extra_eur": self.extra_eur,
            "marginal_eur_per_kw": self.marginal_eur_per_kw,
            "reached": self.reached,
        }


@dataclass(frozen=True)
class CapacityLadder:
    """Remaining cost of ``month`` by peak. With ``state`` it is relative (sunk cost is 0), else absolute."""

    charge_id: str
    month: date
    state: CapacityState | None
    free_up_to_kw: float
    rungs: tuple[LadderRung, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "charge_id": self.charge_id,
            "month": self.month.strftime("%Y-%m"),
            "state": self.state.to_dict() if self.state else None,
            "free_up_to_kw": self.free_up_to_kw,
            "ladder": [rung.to_dict() for rung in self.rungs],
            "unit": UNIT,
        }


def month_bounds(month: date) -> tuple[date, date]:
    """First and last day of the calendar month of ``month``."""
    return month.replace(day=1), month.replace(day=calendar.monthrange(month.year, month.month)[1])


def _parse_bands(raw: object, where: str) -> tuple[CapacityBand, ...]:
    if not isinstance(raw, list) or not raw:
        raise invalid(where, raw)
    bands: list[CapacityBand] = []
    for index, item in enumerate(raw):
        path = f"{where}[{index}]"
        data = as_dict(item, path)
        check_known(data, BAND_FIELDS, path)
        if "up_to_kw" not in data:
            raise missing(f"{path}.up_to_kw")
        up_to = get_number(data, "up_to_kw", path, minimum=0)
        rate = get_number(data, "cent_per_kw_month", path, required=True, minimum=0)
        assert rate is not None
        last = index == len(raw) - 1
        if (up_to is None) != last:
            raise invalid(f"{path}.up_to_kw", up_to)  # only the last band is open-ended, and it must be
        if up_to is not None and bands and bands[-1].up_to_kw is not None and up_to <= bands[-1].up_to_kw:
            raise invalid(f"{path}.up_to_kw", up_to)
        if up_to == 0:
            raise invalid(f"{path}.up_to_kw", up_to)
        bands.append(CapacityBand(up_to, rate))
    return tuple(bands)


def _parse_charge(raw: object, where: str) -> CapacityCharge:
    data = as_dict(raw, where)
    charge_id = get_str(data, "id", where, required=True)
    assert charge_id is not None
    check_known(data, CHARGE_FIELDS, where)
    basis = get_str(data, "basis", where, required=True)
    if basis not in BASES:
        raise invalid(f"{where}.basis", basis)
    min_kw = get_number(data, "min_kw", where, required=True, minimum=0)
    assert min_kw is not None
    if "bands" not in data:
        raise missing(f"{where}.bands")
    valid_from = get_date(data, "valid_from", where)
    valid_to = get_date(data, "valid_to", where)
    if valid_from is not None and valid_from.day != 1:
        raise invalid(f"{where}.valid_from", data["valid_from"])  # a charge covers whole calendar months
    if valid_to is not None and valid_to != month_bounds(valid_to)[1]:
        raise invalid(f"{where}.valid_to", data["valid_to"])
    if valid_from is not None and valid_to is not None and valid_to < valid_from:
        raise invalid(f"{where}.valid_to", data["valid_to"])
    status = get_str(data, "status", where)
    if status is not None and status not in STATUSES:
        raise invalid(f"{where}.status", status)
    return CapacityCharge(
        id=charge_id,
        label=get_str(data, "label", where) or charge_id,
        basis=basis,
        min_kw=min_kw,
        bands=_parse_bands(data["bands"], f"{where}.bands"),
        valid_from=valid_from,
        valid_to=valid_to,
        status=status,
        source=get_str(data, "source", where) or "",
        note=get_str(data, "note", where) or "",
    )


def _overlap(first: CapacityCharge, second: CapacityCharge) -> bool:
    starts_before_end = first.valid_from is None or second.valid_to is None or first.valid_from <= second.valid_to
    ends_after_start = first.valid_to is None or second.valid_from is None or second.valid_from <= first.valid_to
    return starts_before_end and ends_after_start


def parse_capacity_charges(raw: object, where: str, *, require_status: bool) -> tuple[CapacityCharge, ...]:
    """Validate the ``capacity_charges`` list of a grid area; entries must not overlap in validity."""
    if not isinstance(raw, list):
        raise invalid(where, raw)
    charges: list[CapacityCharge] = []
    for index, item in enumerate(raw):
        path = f"{where}[{index}]"
        charge = _parse_charge(item, path)
        if require_status and charge.status is None:
            raise missing(f"{path}.status")
        if any(other.id == charge.id for other in charges):
            raise invalid(f"{path}.id", charge.id)
        if any(_overlap(other, charge) for other in charges):
            raise invalid(f"{path}.valid_from", item.get("valid_from") if isinstance(item, dict) else None)
        charges.append(charge)
    return tuple(charges)


def charge_for_month(charges: tuple[CapacityCharge, ...], month: date, area_id: str) -> CapacityCharge | None:
    """The entry that covers ``month``; ``None`` before the first entry starts (no capacity charge yet).

    A month after the start of the first entry that no entry covers is ``CAPACITY_CHARGE_MISSING``: a gap
    or an outdated list must not turn into a charge of zero.
    """
    for charge in charges:
        if charge.covers(month):
            return charge
    first = month_bounds(month)[0]
    if not charges or all(charge.valid_from is not None and first < charge.valid_from for charge in charges):
        return None
    label = first.strftime("%Y-%m")
    raise EdibertError(
        ErrorCode.CAPACITY_CHARGE_MISSING,
        f"No capacity charge of grid area '{area_id}' covers {label}.",
        area_id=area_id,
        month=label,
    )


def _check_peak(peak_kw: float, field: str) -> float:
    if isinstance(peak_kw, bool) or not isinstance(peak_kw, (int, float)) or peak_kw < 0:
        raise invalid(field, peak_kw)
    return float(peak_kw)


def _raw_eur(charge: CapacityCharge, peak_kw: float) -> float:
    assessed = max(peak_kw, charge.min_kw)
    total = 0.0
    lower = 0.0
    for band in charge.bands:
        upper = assessed if band.up_to_kw is None else min(assessed, band.up_to_kw)
        if upper > lower:
            total += (upper - lower) * band.cent_per_kw_month / 100
        if band.up_to_kw is None or assessed <= band.up_to_kw:
            break
        lower = band.up_to_kw
    return total


def capacity_charge_eur(charge: CapacityCharge, peak_kw: float) -> float:
    """Net amount of one month for a month peak of ``peak_kw`` (minimum and bands applied), in EUR."""
    return round(_raw_eur(charge, _check_peak(peak_kw, "peak_kw")), _EUR_DECIMALS)


def _rate_above(charge: CapacityCharge, kw: float) -> float:
    """EUR per kW for the peak just above ``kw``."""
    for band in charge.bands:
        if band.up_to_kw is None or kw < band.up_to_kw:
            return band.cent_per_kw_month / 100
    raise AssertionError("the last band is open-ended")


def state_month(state: CapacityState, ctx: PricingContext) -> date:
    return ctx.to_local(state.as_of).date().replace(day=1)


def parse_capacity_state(raw: object, where: str = "capacity_state") -> CapacityState:
    """``{peak_15min_kw, as_of}`` from JSON; ``as_of`` is ISO 8601 (naive = local time of the house)."""
    data = as_dict(raw, where)
    check_known(data, ("peak_15min_kw", "as_of"), where)
    peak = get_number(data, "peak_15min_kw", where, required=True, minimum=0)
    text = get_str(data, "as_of", where, required=True)
    assert peak is not None and text is not None
    try:
        as_of = datetime.fromisoformat(text)
    except ValueError as exc:
        raise invalid(f"{where}.as_of", text) from exc
    return CapacityState(peak, as_of)


def capacity_ladder(
    charge: CapacityCharge,
    state: CapacityState | None,
    month: date,
    ctx: PricingContext,
    *,
    step_kw: float | None = None,
    max_kw: float | None = None,
    require_state: bool = False,
) -> CapacityLadder:
    """Remaining cost of ``month`` as a function of the month peak.

    With ``state`` (which must belong to ``month``, else ``CAPACITY_STATE_MONTH_MISMATCH``) a rung at or below
    the larger of ``min_kw`` and the peak so far is ``reached`` with ``extra_eur`` 0 (sunk cost). Without it the
    ladder is absolute (``extra_eur`` is the whole month amount); ``require_state`` makes a missing state
    ``CAPACITY_STATE_MISSING``. Rungs are at 0, the minimum, the peak so far and the band limits, plus every
    ``step_kw`` up to ``max_kw`` (both or neither).
    """
    first = month_bounds(month)[0]
    label = first.strftime("%Y-%m")
    if state is None and require_state:
        raise EdibertError(ErrorCode.CAPACITY_STATE_MISSING, f"No month-to-date peak for {label}.", month=label)
    if state is not None:
        _check_peak(state.peak_15min_kw, "capacity_state.peak_15min_kw")
        actual = state_month(state, ctx)
        if actual != first:
            raise EdibertError(
                ErrorCode.CAPACITY_STATE_MONTH_MISMATCH,
                f"Capacity state of {actual:%Y-%m} does not belong to {label}.",
                month=label,
                state_month=actual.strftime("%Y-%m"),
            )
    if (step_kw is None) != (max_kw is None):
        raise missing("max_kw" if max_kw is None else "step_kw")
    points = {0.0, charge.min_kw}
    points.update(band.up_to_kw for band in charge.bands if band.up_to_kw is not None)
    if step_kw is not None and max_kw is not None:
        if step_kw <= 0:
            raise invalid("step_kw", step_kw)
        count = int(max_kw // step_kw)
        points.update(round(step_kw * index, 6) for index in range(1, count + 1))
        points.add(float(max_kw))
    free = max(charge.min_kw, state.peak_15min_kw) if state is not None else charge.min_kw
    if state is not None:
        points.add(state.peak_15min_kw)
    sunk = _raw_eur(charge, state.peak_15min_kw) if state is not None else 0.0
    rungs = []
    for kw in sorted(points):
        reached = state is not None and kw <= free
        extra = max(_raw_eur(charge, kw) - sunk, 0.0)
        marginal = 0.0 if kw < charge.min_kw or (state is not None and kw < free) else _rate_above(charge, kw)
        rungs.append(LadderRung(kw, round(extra, _LADDER_DECIMALS), round(marginal, _LADDER_DECIMALS), reached))
    return CapacityLadder(charge.id, first, state, free, tuple(rungs))


def months_between(start: date, end: date) -> list[date]:
    """First days of the calendar months that ``[start, end]`` (both dates inclusive) touches."""
    months = []
    current = start.replace(day=1)
    while current <= end:
        months.append(current)
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def capacity_block(
    charges: tuple[CapacityCharge, ...],
    area_id: str,
    state: CapacityState | None,
    ctx: PricingContext,
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """The ``capacity`` list of a price series: one entry per calendar month that ``[start, end)`` touches.

    The state's month gets the relative ladder; a later month starts from a peak of 0 (its state is
    ``{peak_15min_kw: 0, as_of: null}``); an earlier month, or every month without a state, is absolute
    (``state: null``). Months before the first entry starts have no capacity charge and no entry.
    """
    local_start = ctx.to_local(start)
    last_day = (ctx.to_local(end) - timedelta(microseconds=1)).date()
    own_month = state_month(state, ctx) if state is not None else None
    block = []
    for month in months_between(local_start.date(), last_day):
        charge = charge_for_month(charges, month, area_id)
        if charge is None:
            continue
        if own_month is not None and month == own_month:
            ladder = capacity_ladder(charge, state, month, ctx)
            shown: dict[str, Any] | None = ladder.to_dict()["state"]
        elif own_month is not None and month > own_month:
            zero = CapacityState(0.0, ctx.to_local(datetime.combine(month, datetime.min.time())))
            ladder = capacity_ladder(charge, zero, month, ctx)
            shown = {"peak_15min_kw": 0.0, "as_of": None}
        else:
            ladder = capacity_ladder(charge, None, month, ctx)
            shown = None
        first_counted = max(month, local_start.date())
        entry = ladder.to_dict()
        entry["state"] = shown
        entry["days_remaining"] = (month_bounds(month)[1] - first_counted).days + 1
        block.append(entry)
    return block


def check_capacity(
    charges: tuple[CapacityCharge, ...], skipped: Mapping[str, str], area_id: str, state_available: bool
) -> list[EdibertWarning]:
    """Warnings for entries left out by status, non-convex bands and a house that cannot supply the state."""
    found = [
        EdibertWarning(
            WarningCode.GRID_CAPACITY_SKIPPED_STATUS,
            f"Capacity charge '{charge_id}' skipped: status '{status}' is not included.",
            {"charge_id": charge_id, "status": status},
        )
        for charge_id, status in skipped.items()
    ]
    for charge in charges:
        if not charge.convex:
            found.append(
                EdibertWarning(
                    WarningCode.CAPACITY_BANDS_NOT_CONVEX,
                    f"Capacity charge '{charge.id}' has a band rate below the one before it.",
                    {"charge_id": charge.id},
                )
            )
    if charges and not state_available:
        found.append(
            EdibertWarning(
                WarningCode.CAPACITY_STATE_UNAVAILABLE,
                f"Grid area '{area_id}' bills a capacity charge, but the house has no quarter-hour meter.",
                {"area_id": area_id},
            )
        )
    return found
