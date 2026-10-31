"""Price series: the single interface from tariff rules to prices over a horizon.

``tariff_price_series`` evaluates every 15-minute slot between ``start`` and ``end`` and groups them
to the requested resolution (15, 30 or 60 minutes). This is what publishers and the optimizer use.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from edibert._fields import invalid
from edibert.capacity import CapacityState, capacity_block
from edibert.checks import check_grid_fee, check_tariff
from edibert.context import PricingContext
from edibert.errors import EdibertError, EdibertWarning, ErrorCode
from edibert.gridfee import GridFee
from edibert.tariff import IMPORT, PriceResult, Tariff, evaluate

RESOLUTIONS = (15, 30, 60)
QUALITY_EXACT = "exact"
QUALITY_FORECAST = "forecast"
METHOD_EXACT = "exact"  # method of every slot that is not a forecast
_SLOT = timedelta(minutes=15)


@dataclass(frozen=True)
class PricePoint:
    """One price interval. ``cent`` = ``supplier_cent`` + ``grid_cent`` + ``vat_cent`` (rounded).

    ``grid_cent`` is net. For a gross tariff ``supplier_cent`` already includes VAT, so ``vat_cent`` is the VAT
    on the grid fee only. ``market_cent`` is the market price the tariff used (after hourly settlement, mean over
    the point), ``None`` for a tariff that uses none. ``method`` is ``exact`` or, for a forecast point, the
    ``forecast_method`` the caller named (``mirror``, ``hold``, a plug-in name; ``None`` if it named none).
    """

    start: datetime
    end: datetime
    cent: float
    supplier_cent: float
    grid_cent: float
    vat_cent: float
    quality: str
    market_cent: float | None = None
    method: str | None = METHOD_EXACT
    grid_breakdown: tuple[tuple[str, float], ...] | None = None  # net parts of ``grid_cent``; None without grid fee

    def to_dict(self) -> dict[str, Any]:
        result = {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "cent": self.cent,
            "supplier_cent": self.supplier_cent,
            "grid_cent": self.grid_cent,
            "vat_cent": self.vat_cent,
            "quality": self.quality,
            "market_cent": self.market_cent,
            "method": self.method,
        }
        if self.grid_breakdown is not None:
            result["grid_breakdown"] = dict(self.grid_breakdown)
        return result


@dataclass(frozen=True)
class PriceSeries:
    tariff_id: str
    direction: str
    resolution_min: int
    points: tuple[PricePoint, ...]
    warnings: tuple[EdibertWarning, ...]
    capacity: tuple[dict[str, Any], ...] | None = None  # section 5b; None when the grid fee has no capacity charge
    grid_fixed: dict[str, Any] | None = None  # section 5a; the area's fixed yearly amounts, never in a slot price

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tariff_id": self.tariff_id,
            "direction": self.direction,
            "resolution_min": self.resolution_min,
            "unit": "cent/kWh",
            "points": [point.to_dict() for point in self.points],
        }
        if self.capacity is not None:
            result["capacity"] = list(self.capacity)
        if self.grid_fixed is not None:
            result["grid_fixed"] = self.grid_fixed
        return result


def normalize_market(market: Mapping[datetime, float] | None, ctx: PricingContext) -> dict[datetime, float]:
    """Market prices (cent/kWh per 15-minute slot start) keyed by UTC time. Naive keys are local time."""
    return {ctx.to_local(moment).astimezone(UTC): float(value) for moment, value in (market or {}).items()}


def _slot_starts(start: datetime, end: datetime, resolution_min: int) -> list[datetime]:
    if resolution_min not in RESOLUTIONS:
        raise invalid("resolution_min", resolution_min)
    span = (end - start).total_seconds()
    if span <= 0 or span % (resolution_min * 60):
        raise invalid("end", end.isoformat())
    return [start + _SLOT * index for index in range(int(span // _SLOT.total_seconds()))]


def _check_alignment(local_start: datetime, resolution_min: int) -> None:
    if local_start.second or local_start.microsecond or local_start.minute % resolution_min:
        raise invalid("start", local_start.isoformat())


def _market_for(tariff: Tariff, slot: datetime, ctx: PricingContext, market: Mapping[datetime, float]) -> float | None:
    """Market price of the slot; hourly settled spot tariffs use the mean of the four slots of the hour."""
    if not tariff.uses_market_price:
        return None
    if tariff.is_spot and tariff.settlement_mtu == "60min":
        hour = ctx.to_local(slot).replace(minute=0, second=0, microsecond=0).astimezone(UTC)
        keys = [hour + _SLOT * index for index in range(4)]
    else:
        keys = [slot]
    missing_keys = [key for key in keys if key not in market]
    if missing_keys:
        where = ctx.to_local(missing_keys[0]).isoformat()
        raise EdibertError(
            ErrorCode.PRICE_MISSING,
            f"No market price for slot {where} (tariff '{tariff.id}').",
            slot=where,
            tariff_id=tariff.id,
        )
    return sum(market[key] for key in keys) / len(keys)


def _is_forecast(tariff: Tariff, slot: datetime, forecast_from: datetime | None) -> bool:
    return bool(tariff.uses_market_price and forecast_from is not None and slot >= forecast_from)


def _point(
    group: list[tuple[datetime, PriceResult, bool, float | None]], ctx: PricingContext, size: int, forecast_method: str | None
) -> PricePoint:
    results = [item[1] for item in group]
    markets = [item[3] for item in group if item[3] is not None]  # all or none: per tariff
    forecast = any(item[2] for item in group)
    mean_cent = sum(result.cent for result in results) / size
    supplier = sum(result.after_limits_cent for result in results) / size
    grid = sum(result.grid_cent for result in results) / size
    breakdown = None
    if any(result.grid_breakdown for result in results):
        sums: dict[str, float] = {}
        for result in results:
            for part, cent in result.grid_breakdown:
                sums[part] = sums.get(part, 0.0) + cent
        breakdown = tuple((part, round(total / size, 4)) for part, total in sums.items())
    start = ctx.to_local(group[0][0])
    return PricePoint(
        start=start,
        end=ctx.to_local(group[0][0] + _SLOT * size),
        cent=round(mean_cent, 4),
        supplier_cent=round(supplier, 4),
        grid_cent=round(grid, 4),
        vat_cent=round(round(mean_cent, 4) - round(supplier, 4) - round(grid, 4), 4),
        quality=QUALITY_FORECAST if forecast else QUALITY_EXACT,
        market_cent=round(sum(markets) / size, 4) if markets else None,
        method=forecast_method if forecast else METHOD_EXACT,
        grid_breakdown=breakdown,
    )


def _distinct(notes: list[EdibertWarning]) -> list[EdibertWarning]:
    """Each warning once (a fallback month repeats in every slot of the month), in order of first sight."""
    seen: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    result = []
    for note in notes:
        key = (note.code, tuple(sorted((name, str(value)) for name, value in note.params.items())))
        if key not in seen:
            seen.add(key)
            result.append(note)
    return result


def tariff_price_series(
    tariff: Tariff,
    ctx: PricingContext,
    start: datetime,
    end: datetime,
    *,
    resolution_min: int = 15,
    market: Mapping[datetime, float] | None = None,
    forecast_from: datetime | None = None,
    grid_fee: GridFee | None = None,
    capabilities: Collection[str] | None = None,
    forecast_method: str | None = None,
    capacity_state: CapacityState | None = None,
) -> PriceSeries:
    """Prices from ``start`` (inclusive) to ``end`` (exclusive) at the requested resolution.

    ``market`` holds the day-ahead price (cent/kWh) per 15-minute slot start. Slots at or after
    ``forecast_from`` are marked ``forecast`` when the tariff depends on market prices, with
    ``forecast_method`` as their ``method``. A missing price is an error; nothing is carried over or invented.
    A monthly rate taken from another month (Earnie's fallback) is in ``warnings`` as ``MONTH_RATE_FALLBACK``,
    once per requested month.

    For an import tariff whose ``grid_fee`` carries a capacity charge, ``capacity`` holds one block per calendar
    month of the range (section 5b); ``capacity_state`` is the measured month-to-date peak, never assumed.
    The slot prices do not change. The grid area's fixed yearly amounts come as the ``grid_fixed`` block, also never
    folded into a slot price; every point of an import tariff with a grid fee carries ``grid_breakdown``.
    """
    local_start = ctx.to_local(start)
    _check_alignment(local_start, resolution_min)
    slots = _slot_starts(local_start.astimezone(UTC), ctx.to_local(end).astimezone(UTC), resolution_min)
    table = normalize_market(market, ctx)
    forecast_utc = ctx.to_local(forecast_from).astimezone(UTC) if forecast_from else None
    size = resolution_min // 15
    evaluated = []
    for slot in slots:
        market_cent = _market_for(tariff, slot, ctx, table)
        result = evaluate(tariff, slot, ctx, market_cent, grid_fee)
        evaluated.append((slot, result, _is_forecast(tariff, slot, forecast_utc), market_cent))
    points = tuple(_point(evaluated[i : i + size], ctx, size, forecast_method) for i in range(0, len(evaluated), size))
    fallbacks = [note for item in evaluated for note in item[1].warnings]
    notes = check_tariff(tariff, capabilities) + (check_grid_fee(grid_fee) if grid_fee else []) + _distinct(fallbacks)
    capacity = None
    if grid_fee is not None and grid_fee.capacity and tariff.direction == IMPORT:
        capacity = tuple(capacity_block(grid_fee.capacity, grid_fee.area_id, capacity_state, ctx, start, end))
    return PriceSeries(
        tariff.id, tariff.direction, resolution_min, points, tuple(notes), capacity,
        grid_fixed_block(grid_fee) if grid_fee is not None and tariff.direction == IMPORT else None,
    )  # fmt: skip


def grid_fixed_block(grid_fee: GridFee) -> dict[str, Any] | None:
    """The fixed yearly amounts of the grid area as a separate block (net, EUR per year); ``None`` without any."""
    if not grid_fee.fixed:
        return None
    return {
        "area_id": grid_fee.area_id,
        "unit": "EUR per year, net",
        "total_eur_year": round(grid_fee.fixed_eur_year, 2),
        "items": [{"id": part.id, "label": part.label, "eur_year": part.value} for part in grid_fee.fixed],
    }
