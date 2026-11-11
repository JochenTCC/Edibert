"""Comparison of overview rows (Editor P4c): parameters side by side and day curves in one chart (no UI).

At most ``COMPARE_LIMIT`` tariffs; more is an error the UI turns into a message, never a silent cut to the first
few. Day curves are computed like the editor's preview (representative days of a month, house context and grid
fee, market-price tariffs on the example market curve) and put on the table's gross/net basis.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from edibert.context import PricingContext
from edibert.editor.overview import (
    COMPARE_LIMIT,
    Basis,
    Column,
    OverviewRow,
    columns,
    row_values,
)
from edibert.editor.preview import DAY_KEYS, day_curve, representative_dates
from edibert.errors import EdibertError, EdibertWarning, ErrorCode
from edibert.gridfee import GridFee
from edibert.tariff import monthly_rate


class TooManyToCompare(ValueError):
    """More rows than ``COMPARE_LIMIT``: no comparison is drawn."""


def check_count(rows: Sequence[OverviewRow]) -> None:
    if not rows:
        raise ValueError("Nothing to compare.")
    if len(rows) > COMPARE_LIMIT:
        raise TooManyToCompare(f"{len(rows)} tariffs selected; the comparison takes at most {COMPARE_LIMIT}.")
    directions = {row.tariff.direction for row in rows}
    if len(directions) != 1:
        raise ValueError(f"A comparison holds one direction, got {sorted(directions)}.")


@dataclass(frozen=True)
class ParameterLine:
    """One parameter across the compared tariffs (values in the order of the rows)."""

    column: Column
    values: tuple[Any, ...]
    differs: bool


def _comparable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    if isinstance(value, float):
        return round(value, 6)  # gross/net division must not make equal prices look different
    return value


def parameter_lines(rows: Sequence[OverviewRow], basis: Basis, today: date) -> list[ParameterLine]:
    """Every overview column of the direction as one line; ``differs`` when not all tariffs hold the same value.

    The label is left out (it heads the tariff columns); the origin stays, it is a fact about the row.
    """
    check_count(rows)
    cells = [row_values(row, basis, today).values for row in rows]
    lines = []
    for column in columns(rows[0].tariff.direction):
        if column.id == "label":
            continue
        values = tuple(cell[column.id] for cell in cells)
        lines.append(ParameterLine(column, values, len({_comparable(value) for value in values}) > 1))
    return lines


@dataclass(frozen=True)
class CurvePoint:
    row_key: str
    hour: float
    cent: float


@dataclass(frozen=True)
class CurveGap:
    """Why a tariff has no curve for the chosen day: ``no_calendar`` (house without land/region), ``no_holiday``
    (no holiday in that month) or ``error`` (a coded pricing error, e.g. no rate for the month)."""

    row_key: str
    reason: str
    error: EdibertError | None = None


@dataclass(frozen=True)
class Curves:
    day_key: str
    points: tuple[CurvePoint, ...]
    gaps: tuple[CurveGap, ...]
    notes: tuple[tuple[str, EdibertWarning], ...] = ()  # (row key, e.g. MONTH_RATE_FALLBACK)


def _net(cent: float, row: OverviewRow, basis: Basis) -> float:
    """``day_curve`` prices are final prices incl. VAT; the net basis takes the tariff's VAT out again."""
    if basis == Basis.GROSS:
        return cent
    if basis == Basis.NET:
        return cent / (1.0 + row.tariff.vat_percent / 100.0)
    raise ValueError(f"Unknown price basis '{basis}'.")


def _holiday_gap(row: OverviewRow, ctx: PricingContext) -> str:
    try:
        ctx.calendar_for(row.tariff.extra_holiday_dates)
    except EdibertError as err:
        if err.code != ErrorCode.HOLIDAY_REGION_MISSING:
            raise
        return "no_calendar"
    return "no_holiday"


def day_curves(
    rows: Sequence[OverviewRow],
    ctx: PricingContext,
    grid_fee: GridFee | None,
    year: int,
    month: int,
    day_key: str,
    basis: Basis,
) -> Curves:
    """One day curve per tariff for the representative day ``day_key`` of the month; a tariff without that day or
    with a pricing error is a gap with its reason, never left out silently."""
    check_count(rows)
    if day_key not in DAY_KEYS:
        raise ValueError(f"Unknown day type '{day_key}'.")
    points: list[CurvePoint] = []
    gaps: list[CurveGap] = []
    notes: list[tuple[str, EdibertWarning]] = []
    for row in rows:
        try:
            day = representative_dates(ctx, row.tariff, year, month).get(day_key)
            if day is None:
                gaps.append(CurveGap(row.key, _holiday_gap(row, ctx)))
                continue
            curve = day_curve(row.tariff, ctx, day, grid_fee=grid_fee)
            if row.tariff.type == "monthly_table":  # a rate taken from another month is said, as in the preview
                notes.extend((row.key, note) for note in monthly_rate(row.tariff, ctx.to_local(datetime(year, month, 1)))[1])
        except EdibertError as err:
            gaps.append(CurveGap(row.key, "error", err))
            continue
        for point in curve:
            hour = point.start.hour + point.start.minute / 60
            points.append(CurvePoint(row.key, hour, round(_net(point.cent, row, basis), 4)))
    return Curves(day_key, tuple(points), tuple(gaps), tuple(notes))
