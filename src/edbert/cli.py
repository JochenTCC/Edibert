"""Command line.

* ``python -m edbert price --tariff FILE --at 2026-10-12T23:30 --tz Europe/Vienna``
* ``python -m edbert series --tariff FILE --from 2026-12-15T00:00 --to 2026-12-16T00:00 --tz Europe/Vienna``
* ``python -m edbert schema``
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

from edbert._fields import invalid
from edbert.context import PricingContext
from edbert.errors import EdbertError
from edbert.gridfee import (
    GridFee,
    load_grid_fee_catalog,
    load_grid_fee_config,
    resolve_grid_fee,
)
from edbert.i18n import SOURCE_LANGUAGE, SUPPORTED_LANGUAGES, Translator
from edbert.schema import tariff_schema
from edbert.series import RESOLUTIONS, PriceSeries, tariff_price_series
from edbert.store import load_tariff_file
from edbert.tariff import EXPORT, IMPORT, PriceResult, Tariff, evaluate


def _configure_console_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tariff", type=Path, required=True, help="JSON file with one tariff")
    parser.add_argument("--direction", choices=(IMPORT, EXPORT), default=IMPORT)
    parser.add_argument("--tz", required=True, help="IANA time zone of the house, e.g. Europe/Vienna")
    parser.add_argument("--land", help="country for holidays: AT, DE or CH")
    parser.add_argument("--region", help="federal state or canton for holidays")
    parser.add_argument("--grid-fee", type=Path, help="JSON file with the house-profile field 'netznutzung'")
    parser.add_argument("--grid-catalog", type=Path, help="grid_fees.json (Earnie shape) for a catalog area")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edbert", description="Edbert tariff tools (draft).")
    parser.add_argument("--lang", choices=SUPPORTED_LANGUAGES, default=SOURCE_LANGUAGE)
    sub = parser.add_subparsers(dest="command", required=True)
    price = sub.add_parser("price", help="price of one slot for a tariff file")
    _add_common(price)
    price.add_argument("--at", required=True, help="slot start, ISO 8601 (naive = local time)")
    price.add_argument("--epex", type=float, help="day-ahead market price of the slot in cent/kWh")
    series = sub.add_parser("series", help="prices over a time range")
    _add_common(series)
    series.add_argument("--from", dest="start", required=True, help="start, ISO 8601 (inclusive)")
    series.add_argument("--to", dest="end", required=True, help="end, ISO 8601 (exclusive)")
    series.add_argument("--resolution", type=int, choices=RESOLUTIONS, default=60, help="minutes per value")
    series.add_argument("--market-csv", type=Path, help="CSV 'timestamp,cent_kwh' per 15-minute slot")
    series.add_argument("--forecast-from", help="market prices from this time on are forecasts")
    series.add_argument("--format", choices=("table", "json"), default="table")
    series.add_argument("--has", action="append", help="house capability, repeatable (e.g. smart_meter); enables the requirement check")
    sub.add_parser("schema", help="print the JSON Schema of a tariff entry")
    return parser


def _parse_time(text: str | None, field: str) -> datetime | None:
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise invalid(field, text) from exc


def _load_market(path: Path | None, ctx: PricingContext) -> dict[datetime, float]:
    if path is None:
        return {}
    market: dict[datetime, float] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle):
            if not row or not row[0].strip() or row[0].strip().lower() in ("timestamp", "time", "start"):
                continue
            moment = _parse_time(row[0].strip(), "market-csv")
            if moment is None or len(row) < 2:
                raise invalid("market-csv", row)
            try:
                market[ctx.to_local(moment)] = float(row[1])
            except ValueError as exc:
                raise invalid("market-csv", row[1]) from exc
    return market


def _context_and_grid(args: argparse.Namespace) -> tuple[PricingContext, GridFee | None]:
    ctx = PricingContext(args.tz, args.land, args.region)
    if args.grid_fee is None:
        return ctx, None
    catalog = load_grid_fee_catalog(args.grid_catalog) if args.grid_catalog else None
    return ctx, resolve_grid_fee(load_grid_fee_config(args.grid_fee), catalog)


def _price_lines(t: Translator, tariff: Tariff, result: PriceResult, local: datetime, tz: str) -> list[str]:
    n = t.number
    lines = [
        t.t("cli.tariff", label=tariff.label, tariff_id=tariff.id),
        t.t("cli.slot", slot=local.strftime("%Y-%m-%d %H:%M"), timezone=tz),
        t.t("cli.base", cent=n(result.base_cent)),
        t.t("cli.rule", rule=result.rule_id) if result.rule_id else t.t("cli.no_rule"),
    ]
    if result.after_limits_cent != result.after_rule_cent:
        lines.append(t.t("cli.after_limits", cent=n(result.after_limits_cent)))
    if result.grid_cent:
        lines.append(t.t("cli.grid", cent=n(result.grid_cent)))
        if result.grid_rule_id:
            lines.append(t.t("cli.grid_rule", rule=result.grid_rule_id))
    if tariff.prices_include_vat:
        lines.append(t.t("cli.price", cent=n(result.cent)))
    else:
        lines.append(t.t("cli.price_incl_vat", vat=n(tariff.vat_percent), cent=n(result.cent)))
    return lines


def run_price(args: argparse.Namespace, t: Translator) -> list[str]:
    tariff = load_tariff_file(args.tariff, args.direction)
    ctx, grid_fee = _context_and_grid(args)
    slot = _parse_time(args.at, "--at")
    assert slot is not None
    result = evaluate(tariff, slot, ctx, args.epex, grid_fee)
    return _price_lines(t, tariff, result, ctx.to_local(slot), args.tz)


def _series_lines(t: Translator, series: PriceSeries) -> list[str]:
    lines = [
        t.t("cli.series_title", tariff_id=series.tariff_id, resolution=series.resolution_min, count=len(series.points))
    ]
    for point in series.points:
        start = point.start.strftime("%Y-%m-%d %H:%M")
        lines.append(t.t("cli.series_row", start=start, cent=t.number(point.cent), quality=point.quality))
    return lines


def run_series(args: argparse.Namespace, t: Translator) -> tuple[list[str], list[str]]:
    tariff = load_tariff_file(args.tariff, args.direction)
    ctx, grid_fee = _context_and_grid(args)
    start, end = _parse_time(args.start, "--from"), _parse_time(args.end, "--to")
    assert start is not None and end is not None
    series = tariff_price_series(
        tariff, ctx, start, end,
        resolution_min=args.resolution,
        market=_load_market(args.market_csv, ctx),
        forecast_from=_parse_time(args.forecast_from, "--forecast-from"),
        grid_fee=grid_fee,
        capabilities=set(args.has) if args.has else None,
    )  # fmt: skip
    notes = [t.warning(item) for item in series.warnings]
    if args.format == "json":
        return [json.dumps(series.to_dict(), indent=2, ensure_ascii=False)], notes
    return _series_lines(t, series), notes


def main(argv: list[str] | None = None) -> int:
    _configure_console_utf8()
    args = build_parser().parse_args(argv)
    t = Translator(args.lang)
    if args.command == "schema":
        print(json.dumps(tariff_schema(), indent=2, ensure_ascii=False))
        return 0
    try:
        if args.command == "price":
            lines, notes = run_price(args, t), []
        else:
            lines, notes = run_series(args, t)
    except (EdbertError, OSError) as err:
        message = t.error(err) if isinstance(err, EdbertError) else str(err)
        print(t.t("cli.error", message=message), file=sys.stderr)
        return 2
    print("\n".join(lines))
    for note in notes:
        print(note, file=sys.stderr)
    return 0
