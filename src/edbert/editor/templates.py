"""Quick templates for the time-window step: one click creates the usual rows."""

from __future__ import annotations

from edbert.editor.model import DAY_NAMES, RuleDraft, slugify
from edbert.i18n import Translator
from edbert.rules import MODE_ABSOLUTE, MODE_ADD

TEMPLATES = ("night", "weekend", "summer_midday", "ht_st_nt")


def _unique(rule_id: str, taken: set[str]) -> str:
    candidate, number = rule_id, 2
    while candidate in taken:
        candidate, number = f"{rule_id}_{number}", number + 1
    taken.add(candidate)
    return candidate


def _rule(t: Translator, key: str, taken: set[str], spot: bool, base: float, factor: float, **fields) -> RuleDraft:
    label = t.t(f"editor.rule.{key}")
    value = 0.0 if spot else round(base * factor, 2)
    return RuleDraft(
        id=_unique(slugify(key), taken), label=label, mode=MODE_ADD if spot else MODE_ABSOLUTE, value=value, **fields
    )


def rules_for_template(
    name: str, t: Translator, *, kind: str, base_cent: float, taken_ids: set[str] | None = None
) -> list[RuleDraft]:
    """Rows for a template. For spot tariffs the rows are surcharges (value 0 to fill in), otherwise prices.

    ``base_cent`` only seeds the suggested values (a guess the user is expected to correct).
    """
    taken = set(taken_ids or ())
    spot = kind == "spot"
    if name == "night":
        return [_rule(t, "night", taken, spot, base_cent, 0.8, start="22:00", end="06:00")]
    if name == "weekend":
        return [_rule(t, "weekend", taken, spot, base_cent, 0.9, days=list(DAY_NAMES[5:]))]
    if name == "summer_midday":
        return [_rule(t, "summer_midday", taken, spot, base_cent, 0.9, start="10:00", end="16:00", months=[4, 5, 6, 7, 8, 9])]
    if name == "ht_st_nt":
        return [
            _rule(t, "low_tariff", taken, spot, base_cent, 0.4, start="00:00", end="06:00"),
            _rule(t, "high_tariff", taken, spot, base_cent, 1.4, start="17:00", end="21:00"),
        ]
    raise ValueError(f"Unknown template '{name}'. Known: {', '.join(TEMPLATES)}.")
