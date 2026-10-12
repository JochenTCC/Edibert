"""Preview data for the editor: price curves of typical days and an example market curve."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime, timedelta

from edbert.context import PricingContext
from edbert.errors import EdbertError, ErrorCode
from edbert.gridfee import GridFee
from edbert.series import PricePoint, tariff_price_series
from edbert.tariff import Tariff

DAY_KEYS = ("weekday", "saturday", "sunday", "holiday")


def example_market_profile() -> tuple[float, ...]:
    """Day-ahead price (cent/kWh) per 15 minutes of an illustrative day: cheap night, PV dip, evening peak.

    Made up for the preview of spot tariffs; it is not a forecast.
    """
    values: list[float] = []
    for index in range(96):
        hour = index / 4
        price = 9.0
        price += 4.0 if 6 <= hour < 9 else 0.0
        price -= 5.0 if 11 <= hour < 15 else 0.0
        price += 7.0 if 17 <= hour < 20 else 0.0
        price -= 2.0 if hour < 5 else 0.0
        values.append(price)
    return tuple(values)


def representative_dates(ctx: PricingContext, tariff: Tariff, year: int, month: int) -> dict[str, date]:
    """First Wednesday, Saturday and Sunday of the month and, if a calendar is available, the first holiday."""
    days = {key: None for key in DAY_KEYS}
    for number in range(1, calendar.monthrange(year, month)[1] + 1):
        when = date(year, month, number)
        for key, weekday in (("weekday", 2), ("saturday", 5), ("sunday", 6)):
            if days[key] is None and when.weekday() == weekday:
                days[key] = when
    try:
        cal = ctx.calendar_for(tariff.extra_holiday_dates)
    except EdbertError as err:
        if err.code != ErrorCode.HOLIDAY_REGION_MISSING:
            raise
        cal = None
    if cal is not None:
        days["holiday"] = next((d for n in range(1, 32) if (d := _safe_date(year, month, n)) and cal.is_holiday(d)), None)
    return {key: value for key, value in days.items() if value is not None}


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def day_curve(
    tariff: Tariff,
    ctx: PricingContext,
    day: date,
    *,
    grid_fee: GridFee | None = None,
    market_profile: tuple[float, ...] | None = None,
) -> tuple[PricePoint, ...]:
    """The prices of one local day (96 values; 92 or 100 on daylight-saving days).

    Spot tariffs use ``market_profile`` by local time of day (default: the example curve).
    """
    start = datetime(day.year, day.month, day.day)
    end = start + timedelta(days=1)
    market = None
    if tariff.uses_market_price:
        profile = market_profile or example_market_profile()
        first, last = ctx.to_local(start).astimezone(UTC), ctx.to_local(end).astimezone(UTC)
        market = {}
        slot = first
        while slot < last:
            local = ctx.to_local(slot)
            market[slot] = profile[(local.hour * 60 + local.minute) // 15]
            slot += timedelta(minutes=15)
    return tariff_price_series(tariff, ctx, start, end, resolution_min=15, market=market, grid_fee=grid_fee).points
