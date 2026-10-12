"""Command line: ``python -m edbert price --tariff FILE --at 2026-10-12T23:30 --tz Europe/Vienna``."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from edbert._fields import invalid
from edbert.context import PricingContext
from edbert.errors import EdbertError
from edbert.i18n import SOURCE_LANGUAGE, SUPPORTED_LANGUAGES, Translator
from edbert.schema import tariff_schema
from edbert.store import load_tariff_file
from edbert.tariff import EXPORT, IMPORT, PriceResult, Tariff, evaluate


def _configure_console_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="edbert", description="Edbert tariff tools (draft).")
    parser.add_argument("--lang", choices=SUPPORTED_LANGUAGES, default=SOURCE_LANGUAGE)
    sub = parser.add_subparsers(dest="command", required=True)
    price = sub.add_parser("price", help="price of one slot for a tariff file")
    price.add_argument("--tariff", type=Path, required=True, help="JSON file with one tariff")
    price.add_argument("--direction", choices=(IMPORT, EXPORT), default=IMPORT)
    price.add_argument("--at", required=True, help="slot start, ISO 8601 (naive = local time)")
    price.add_argument("--tz", required=True, help="IANA time zone of the house, e.g. Europe/Vienna")
    price.add_argument("--epex", type=float, help="day-ahead market price of the slot in cent/kWh")
    price.add_argument("--land", help="country for holidays: AT, DE or CH")
    price.add_argument("--region", help="federal state or canton for holidays")
    sub.add_parser("schema", help="print the JSON Schema of a tariff entry")
    return parser


def _lines(t: Translator, tariff: Tariff, result: PriceResult, local: datetime, tz: str) -> list[str]:
    n = t.number
    lines = [
        t.t("cli.tariff", label=tariff.label, tariff_id=tariff.id),
        t.t("cli.slot", slot=local.strftime("%Y-%m-%d %H:%M"), timezone=tz),
        t.t("cli.base", cent=n(result.base_cent)),
        t.t("cli.rule", rule=result.rule_id) if result.rule_id else t.t("cli.no_rule"),
    ]
    if result.after_limits_cent != result.after_rule_cent:
        lines.append(t.t("cli.after_limits", cent=n(result.after_limits_cent)))
    if tariff.prices_include_vat:
        lines.append(t.t("cli.price", cent=n(result.cent)))
    else:
        lines.append(t.t("cli.price_incl_vat", vat=n(tariff.vat_percent), cent=n(result.cent)))
    return lines


def run_price(args: argparse.Namespace, t: Translator) -> list[str]:
    tariff = load_tariff_file(args.tariff, args.direction)
    ctx = PricingContext(args.tz, args.land, args.region)
    try:
        slot = datetime.fromisoformat(args.at)
    except ValueError as exc:
        raise invalid("--at", args.at) from exc
    result = evaluate(tariff, slot, ctx, args.epex)
    return _lines(t, tariff, result, ctx.to_local(slot), args.tz)


def main(argv: list[str] | None = None) -> int:
    _configure_console_utf8()
    args = build_parser().parse_args(argv)
    t = Translator(args.lang)
    if args.command == "schema":
        print(json.dumps(tariff_schema(), indent=2, ensure_ascii=False))
        return 0
    try:
        print("\n".join(run_price(args, t)))
    except EdbertError as err:
        print(t.t("cli.error", message=t.error(err)), file=sys.stderr)
        return 2
    return 0
