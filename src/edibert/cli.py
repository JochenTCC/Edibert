"""Command line.

* ``python -m edibert price --tariff FILE --at 2026-10-12T23:30 --tz Europe/Vienna``
* ``python -m edibert series --tariff FILE --from 2026-12-15T00:00 --to 2026-12-16T00:00 --tz Europe/Vienna``
* ``python -m edibert capacity --grid-fee FILE --month 2027-01 --tz Europe/Vienna --peak-so-far 4.2 --as-of 2027-01-14T18:00``
* ``python -m edibert package verify FILE``
* ``python -m edibert package import FILE --catalog tariffs.json --grid-catalog grid_fees.json [--keep-local KEY]``
* ``python -m edibert exchange fetch|status|report ...`` (server exchange, ``docs/spec/catalog-exchange.md``)
* ``python -m edibert schema``
* ``python -m edibert publish --data-dir DIR [--once] [--dry-run]``
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from edibert._fields import invalid, missing
from edibert.capacity import (
    CapacityState,
    capacity_charge_eur,
    capacity_ladder,
    charge_for_month,
)
from edibert.catalog_import import (
    KEEP_LOCAL,
    TAKE_PACKAGE,
    apply_package_import,
    plan_package_import,
    write_catalog_pair,
)
from edibert.checks import check_grid_fee
from edibert.context import PricingContext
from edibert.errors import EdibertError, ErrorCode
from edibert.gridfee import (
    GridFee,
    load_grid_fee_config,
    load_grid_fees,
    resolve_grid_fee,
)
from edibert.i18n import SOURCE_LANGUAGE, SUPPORTED_LANGUAGES, Translator
from edibert.package import load_trusted_keys, read_package, verify_package
from edibert.report import price_lines
from edibert.schema import tariff_schema
from edibert.series import RESOLUTIONS, PriceSeries, tariff_price_series
from edibert.store import load_tariff_file
from edibert.tariff import EXPORT, IMPORT, evaluate


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
    parser.add_argument("--grid-fee", type=Path, help="JSON file with the house-profile field 'netznutzung' (selects a grid area)")
    parser.add_argument("--grid-catalog", type=Path, help="grid_fees.json (Earnie shape) with catalog areas")
    parser.add_argument("--user-grid-fees", type=Path, help="user_grid_fees.json with own grid areas (user_...)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edibert", description="Edibert tariff tools (draft).")
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
    series.add_argument("--forecast-method", help="method of the forecast prices (mirror, hold, plug-in name)")
    series.add_argument("--format", choices=("table", "json"), default="table")
    series.add_argument("--has", action="append", help="house capability, repeatable (e.g. smart_meter); enables the requirement check")
    capacity = sub.add_parser("capacity", help="capacity charge of one month: amount for a peak and the cost ladder")
    capacity.add_argument("--grid-fee", type=Path, required=True, help="JSON file with the house-profile field 'netznutzung'")
    capacity.add_argument("--grid-catalog", type=Path, help="grid_fees.json with catalog areas")
    capacity.add_argument("--user-grid-fees", type=Path, help="user_grid_fees.json with own grid areas (user_...)")
    capacity.add_argument("--tz", required=True, help="IANA time zone of the house, e.g. Europe/Vienna")
    capacity.add_argument("--month", required=True, help="calendar month, YYYY-MM")
    capacity.add_argument("--peak-so-far", type=float, help="measured month-to-date peak in kW (needs --as-of)")
    capacity.add_argument("--as-of", help="time of the month-to-date peak state, ISO 8601 (naive = local time)")
    capacity.add_argument("--power", type=float, help="month peak in kW to compute the month amount for")
    capacity.add_argument("--step", type=float, help="extra ladder rungs every STEP kW (needs --max)")
    capacity.add_argument("--max", dest="max_kw", type=float, help="highest ladder rung in kW (with --step)")
    capacity.add_argument("--format", choices=("table", "json"), default="table")
    package = sub.add_parser("package", help="check or import a signed catalog package")
    package_sub = package.add_subparsers(dest="package_command", required=True)
    verify = package_sub.add_parser("verify", help="check signature and content of a package")
    verify.add_argument("file", type=Path)
    verify.add_argument("--trusted-keys", type=Path, help='JSON {"<key_id>": "<base64 public key>"} used instead of the built-in keys')
    verify.add_argument("--format", choices=("table", "json"), default="table")
    imports = package_sub.add_parser("import", help="replace the catalog files with a package")
    imports.add_argument("file", type=Path)
    imports.add_argument("--trusted-keys", type=Path, help='JSON {"<key_id>": "<base64 public key>"} used instead of the built-in keys')
    imports.add_argument("--catalog", type=Path, required=True, help="tariffs.json to replace")
    imports.add_argument("--grid-catalog", type=Path, required=True, help="grid_fees.json to replace")
    imports.add_argument("--keep-local", action="append", default=[], metavar="KEY", help="keep this locally entered monthly rate (repeatable)")
    imports.add_argument("--take-package", action="append", default=[], metavar="KEY", help="take the package's value for this monthly rate (repeatable)")
    imports.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    exchange = sub.add_parser("exchange", help="exchange with the tariff database server (EDIBERT_EXCHANGE_OFF=1 switches it off)")
    exchange_sub = exchange.add_subparsers(dest="exchange_command", required=True)
    fetch = exchange_sub.add_parser("fetch", help="download the latest catalog package (checked tariffs, signed)")
    fetch.add_argument("--out", type=Path, required=True, help="package file to write; check and import it with 'package import'")
    fetch.add_argument("--catalog", type=Path, help="current tariffs.json: nothing is downloaded while its package is the latest")
    templates = exchange_sub.add_parser("templates", help="list unchecked templates of the tariff database (copy them in the editor)")
    templates.add_argument("--land", required=True, help="two letters, e.g. AT")
    templates.add_argument("--direction", choices=("import", "export", "grid"), required=True)
    templates.add_argument("--grid-area", help="grid area ID (only with --direction grid)")
    templates.add_argument("--supplier", help="search in supplier ID and label (at least 2 characters)")
    templates.add_argument("--format", choices=("table", "json"), default="table")
    for name, text in (("status", "status of the tariffs in use (check state, newest version, reliable)"),
                       ("report", "report use of the tariffs in use, one request per tariff at random times within 24 h")):
        command = exchange_sub.add_parser(name, help=text)
        command.add_argument("--data-dir", type=Path, default=Path("edibert_data"), help="folder with publish.json and user_tariffs.json")
        command.add_argument("--catalog", type=Path, help="tariffs.json the catalog tariffs come from")
        command.add_argument("--config", type=Path, help="publish.json naming the tariffs in use (default: in the data folder)")
        if name == "report":
            command.add_argument("--no-delay", action="store_true", help="send right away instead of at random times")
    sub.add_parser("schema", help="print the JSON Schema of a tariff entry")
    ui = sub.add_parser("ui", help="start the tariff editor in the browser (needs: pip install 'edibert[ui]')")
    ui.add_argument("--data-dir", type=Path, default=Path("edibert_data"), help="folder for user_tariffs.json and house.json")
    ui.add_argument("--catalog", type=Path, help="tariffs.json to copy tariffs from")
    ui.add_argument("--port", type=int, default=8501)
    publish = sub.add_parser("publish", help="publish prices to an MQTT broker (needs: pip install 'edibert[mqtt]')")
    publish.add_argument("--data-dir", type=Path, default=Path("edibert_data"), help="folder with publish.json, house.json and user_tariffs.json")
    publish.add_argument("--catalog", type=Path, help="tariffs.json to take catalog tariffs from")
    publish.add_argument("--config", type=Path, help="publish.json (default: in the data folder)")
    publish.add_argument("--once", action="store_true", help="publish one time and exit")
    publish.add_argument("--dry-run", action="store_true", help="print the topics instead of sending them")
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
    catalog = load_grid_fees(args.grid_catalog, args.user_grid_fees)
    return ctx, resolve_grid_fee(load_grid_fee_config(args.grid_fee), catalog)


def run_price(args: argparse.Namespace, t: Translator) -> list[str]:
    tariff = load_tariff_file(args.tariff, args.direction)
    ctx, grid_fee = _context_and_grid(args)
    slot = _parse_time(args.at, "--at")
    assert slot is not None
    result = evaluate(tariff, slot, ctx, args.epex, grid_fee)
    return price_lines(t, tariff, result, ctx.to_local(slot), args.tz)


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
        forecast_method=args.forecast_method,
        grid_fee=grid_fee,
        capabilities=set(args.has) if args.has else None,
    )  # fmt: skip
    notes = [t.warning(item) for item in series.warnings]
    if args.format == "json":
        return [json.dumps(series.to_dict(), indent=2, ensure_ascii=False)], notes
    return _series_lines(t, series), notes


def _parse_month(text: str) -> date:
    try:
        return datetime.strptime(text, "%Y-%m").date()
    except ValueError as exc:
        raise invalid("--month", text) from exc


def _capacity_state(args: argparse.Namespace) -> CapacityState | None:
    if args.peak_so_far is None and args.as_of is None:
        return None
    if args.peak_so_far is None:
        raise missing("--peak-so-far")
    as_of = _parse_time(args.as_of, "--as-of")
    if as_of is None:
        raise missing("--as-of")
    return CapacityState(args.peak_so_far, as_of)


def run_capacity(args: argparse.Namespace, t: Translator) -> tuple[list[str], list[str]]:
    ctx = PricingContext(args.tz)
    grid_fee = resolve_grid_fee(load_grid_fee_config(args.grid_fee), load_grid_fees(args.grid_catalog, args.user_grid_fees))
    notes = [t.warning(item) for item in check_grid_fee(grid_fee)]
    month = _parse_month(args.month)
    charge = charge_for_month(grid_fee.capacity, month, grid_fee.area_id)
    if charge is None:
        return [t.t("cli.capacity_none", area_id=grid_fee.area_id, month=args.month)], notes
    ladder = capacity_ladder(charge, _capacity_state(args), month, ctx, step_kw=args.step, max_kw=args.max_kw)
    amount = capacity_charge_eur(charge, args.power) if args.power is not None else None
    if args.format == "json":
        result = ladder.to_dict()
        if amount is not None:
            result["power_kw"], result["amount_eur"] = args.power, amount
        return [json.dumps(result, indent=2, ensure_ascii=False)], notes
    lines = [t.t("cli.capacity_title", charge_id=charge.id, month=args.month, free=t.number(ladder.free_up_to_kw))]
    if amount is not None:
        lines.append(t.t("cli.capacity_amount", power=t.number(args.power), eur=t.number(amount)))
    for rung in ladder.rungs:
        row = t.t(
            "cli.capacity_row",
            kw=t.number(rung.up_to_kw),
            extra=t.number(rung.extra_eur),
            marginal=t.number(rung.marginal_eur_per_kw),
        )
        lines.append(f"{row}  [{t.t('cli.capacity_reached')}]" if rung.reached else row)
    return lines, notes


def _read_optional(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc


def run_package(args: argparse.Namespace, t: Translator) -> tuple[list[str], list[str]]:
    keys = load_trusted_keys(args.trusted_keys) if args.trusted_keys else None
    package = verify_package(read_package(args.file), trusted_keys=keys)
    notes = [t.warning(item) for item in package.warnings]
    manifest = package.manifest
    if args.package_command == "verify":
        if args.format == "json":
            return [json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False)], notes
        return [t.t("cli.package_ok", package_id=manifest.package_id,
                    issued_at=manifest.issued_at.isoformat(), valid_until=manifest.valid_until.isoformat())], notes  # fmt: skip
    plan = plan_package_import(package, _read_optional(args.catalog), _read_optional(args.grid_catalog))
    lines = [f"{item.change}: {item.key}" for item in plan.changes]
    for conflict in plan.conflicts:
        package_cent = "-" if conflict.package_cent is None else t.number(conflict.package_cent)
        lines.append(t.t("cli.package_conflict", entry=conflict.key, local=t.number(conflict.local_cent), package=package_cent))
    if args.dry_run:
        return [*lines, t.t("cli.package_dry_run")], notes
    resolutions = {key: KEEP_LOCAL for key in args.keep_local} | {key: TAKE_PACKAGE for key in args.take_package}
    tariffs, grid_fees = apply_package_import(plan, resolutions)
    write_catalog_pair(args.catalog, tariffs, args.grid_catalog, grid_fees)
    return [*lines, t.t("cli.package_done", package_id=manifest.package_id)], notes


def run_ui(args: argparse.Namespace, t: Translator) -> int:
    """Start Streamlit with the editor page. Settings travel as environment variables."""
    if importlib.util.find_spec("streamlit") is None:
        print(t.t("cli.ui_missing"), file=sys.stderr)
        return 2
    from edibert.ui import app, config

    env = {**os.environ, config.ENV_DATA_DIR: str(args.data_dir), config.ENV_LANG: args.lang}
    if args.catalog:
        env[config.ENV_CATALOG] = str(args.catalog)
    print(t.t("cli.ui_start", path=str(args.data_dir)))
    command = [sys.executable, "-m", "streamlit", "run", str(Path(app.__file__)), "--server.port", str(args.port),
               "--server.headless", "true", "--browser.gatherUsageStats", "false"]  # fmt: skip
    return subprocess.call(command, env=env)


def main(argv: list[str] | None = None) -> int:
    _configure_console_utf8()
    args = build_parser().parse_args(argv)
    t = Translator(args.lang)
    if args.command == "schema":
        print(json.dumps(tariff_schema(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "ui":
        return run_ui(args, t)
    try:
        if args.command == "publish":
            from edibert.publish.command import run_publish

            return run_publish(args, t)
        if args.command == "price":
            lines, notes = run_price(args, t), []
        elif args.command == "capacity":
            lines, notes = run_capacity(args, t)
        elif args.command == "package":
            lines, notes = run_package(args, t)
        elif args.command == "exchange":
            from edibert.publish.exchange_command import run_exchange

            lines, notes = run_exchange(args, t), []
        else:
            lines, notes = run_series(args, t)
    except (EdibertError, OSError) as err:
        message = t.error(err) if isinstance(err, EdibertError) else str(err)
        print(t.t("cli.error", message=message), file=sys.stderr)
        return 2
    print("\n".join(lines))
    for note in notes:
        print(note, file=sys.stderr)
    return 0
