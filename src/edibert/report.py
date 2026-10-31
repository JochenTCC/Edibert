"""Text lines that explain one slot price (shared by the command line and the editor)."""

from __future__ import annotations

from datetime import datetime

from edibert.gridfee import GridFee
from edibert.i18n import Translator
from edibert.tariff import PriceResult, Tariff


def price_lines(t: Translator, tariff: Tariff, result: PriceResult, local: datetime, tz: str) -> list[str]:
    """Lines: tariff, slot, base price, rule, floor/cap, grid fee (with its parts), final price."""
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
        if len(result.grid_breakdown) > 1:  # work price plus the area's components
            for part, cent in result.grid_breakdown:
                lines.append(t.t("cli.grid_part", part=part, cent=n(cent)))
    if tariff.prices_include_vat:
        lines.append(t.t("cli.price", cent=n(result.cent)))
    else:
        lines.append(t.t("cli.price_incl_vat", vat=n(tariff.vat_percent), cent=n(result.cent)))
    return lines


def grid_fixed_lines(t: Translator, grid_fee: GridFee | None) -> list[str]:
    """The grid area's fixed yearly amounts (net), one line each and the total; empty without any."""
    if grid_fee is None or not grid_fee.fixed:
        return []
    lines = [t.t("cli.grid_fixed", label=part.label, eur=t.number(part.value, 2)) for part in grid_fee.fixed]
    lines.append(t.t("cli.grid_fixed_total", eur=t.number(grid_fee.fixed_eur_year, 2), area_id=grid_fee.area_id))
    return lines
