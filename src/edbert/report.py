"""Text lines that explain one slot price (shared by the command line and the editor)."""

from __future__ import annotations

from datetime import datetime

from edbert.i18n import Translator
from edbert.tariff import PriceResult, Tariff


def price_lines(t: Translator, tariff: Tariff, result: PriceResult, local: datetime, tz: str) -> list[str]:
    """Lines: tariff, slot, base price, rule, floor/cap, grid fee, final price."""
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
