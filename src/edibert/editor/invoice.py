"""Invoice check: recompute one month from the kWh per price band and compare with the real invoice."""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from edibert._fields import invalid
from edibert.context import PricingContext
from edibert.gridfee import GridFee
from edibert.rules import day_info, matching_rule
from edibert.tariff import EXPORT, Tariff, evaluate

BASE_BAND = "base"
TOLERANCE_PERCENT = 2.0  # deviation up to this is "ok"; rounding on invoices explains small gaps


@dataclass(frozen=True)
class Band:
    """A price band of a month: the base price (no rule) or the price while one rule applies."""

    id: str
    label: str
    cent: float  # final price in cent/kWh, incl. grid fee and VAT as configured


@dataclass(frozen=True)
class InvoiceCheck:
    expected_eur: float
    invoice_eur: float
    energy_eur: float
    fees_eur: float
    deviation_percent: float
    ok: bool
    grid_fixed_eur: float = 0.0  # the grid area's fixed amounts for the month, with the tariff's VAT


def _slots_of_month(month: date):
    for number in range(1, calendar.monthrange(month.year, month.month)[1] + 1):
        for index in range(96):
            yield datetime(month.year, month.month, number, index // 4, index % 4 * 15)


def invoice_bands(
    tariff: Tariff,
    ctx: PricingContext,
    month: date,
    *,
    market_cent: float | None = None,
    grid_fee: GridFee | None = None,
) -> list[Band]:
    """Bands that occur in the month, each priced at a slot where it is the first matching rule.

    ``market_cent`` is the month's average market price and is needed for spot tariffs.
    """
    found: dict[str, Band] = {}
    wanted = {BASE_BAND, *(rule.id for rule in tariff.rules)}
    for slot in _slots_of_month(month):
        local = ctx.to_local(slot)
        info = day_info(tariff.rules, tariff.holiday_mode, tariff.extra_holiday_dates, local, ctx)
        rule = matching_rule(
            tariff.rules, local, info, holiday_mode=tariff.holiday_mode, epex_cent=market_cent, tariff_id=tariff.id
        )
        key = rule.id if rule else BASE_BAND
        if key not in found:
            found[key] = Band(key, rule.label if rule else BASE_BAND, evaluate(tariff, slot, ctx, market_cent, grid_fee).cent)
        if len(found) == len(wanted):
            break
    return list(found.values())


def monthly_fees_eur(tariff: Tariff) -> float:
    """Fixed monthly fees as they appear on the invoice (gross, like the work price)."""
    total = sum(tariff.fees.values())
    return total if tariff.prices_include_vat else total * (1.0 + tariff.vat_percent / 100.0)


def grid_fixed_month_eur(tariff: Tariff, grid_fee: GridFee | None) -> float:
    """One twelfth of the grid area's fixed yearly amounts (net) with the tariff's VAT, as on the invoice."""
    if grid_fee is None or tariff.direction == EXPORT:
        return 0.0
    return grid_fee.fixed_eur_year / 12.0 * (1.0 + tariff.vat_percent / 100.0)


def invoice_check(
    tariff: Tariff,
    ctx: PricingContext,
    month: date,
    kwh_by_band: Mapping[str, float],
    invoice_eur: float,
    *,
    market_cent: float | None = None,
    grid_fee: GridFee | None = None,
) -> InvoiceCheck:
    """Compare the invoice total with kWh per band times band price plus the monthly fees and the grid area's
    fixed amounts (one twelfth of the yearly amount)."""
    if tariff.direction == EXPORT or invoice_eur <= 0:
        raise invalid("invoice_eur", invoice_eur)
    bands = {band.id: band for band in invoice_bands(tariff, ctx, month, market_cent=market_cent, grid_fee=grid_fee)}
    for band_id in kwh_by_band:
        if band_id not in bands:
            raise invalid(f"kwh_by_band.{band_id}", band_id)
    energy = sum(kwh * bands[band_id].cent / 100.0 for band_id, kwh in kwh_by_band.items())
    fees = monthly_fees_eur(tariff)
    grid_fixed = grid_fixed_month_eur(tariff, grid_fee)
    expected = energy + fees + grid_fixed
    deviation = (expected - invoice_eur) / invoice_eur * 100.0
    return InvoiceCheck(
        round(expected, 2), round(invoice_eur, 2), round(energy, 2), round(fees, 2), round(deviation, 2),
        abs(deviation) <= TOLERANCE_PERCENT, round(grid_fixed, 2),
    )  # fmt: skip


__all__ = ["BASE_BAND", "Band", "InvoiceCheck", "grid_fixed_month_eur", "invoice_bands", "invoice_check", "monthly_fees_eur", "timedelta"]
