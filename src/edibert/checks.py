"""Non-fatal checks: findings the UI shows as warnings (never an error, never silent)."""

from __future__ import annotations

from collections.abc import Collection

from edibert.capacity import check_capacity
from edibert.errors import EdibertWarning, WarningCode
from edibert.gridfee import SKIP_NO_QUARTER_HOUR_METER, SKIP_STATUS, GridFee
from edibert.tariff import Tariff

_MINUTES_PER_HOUR = 60


def _unaligned_rules(tariff: Tariff) -> list[str]:
    return [
        rule.id
        for rule in tariff.rules
        if rule.from_min % _MINUTES_PER_HOUR or rule.to_min % _MINUTES_PER_HOUR
    ]


def check_tariff(tariff: Tariff, capabilities: Collection[str] | None = None) -> list[EdibertWarning]:
    """Warnings for a tariff.

    * a rule window that is not hour-aligned in a tariff settled hourly (``settlement_mtu`` 60min)
    * requirements (tariff or rule) that are not among the house ``capabilities`` (if given)
    """
    found: list[EdibertWarning] = []
    if tariff.is_spot and tariff.settlement_mtu == "60min":
        for rule_id in _unaligned_rules(tariff):
            found.append(
                EdibertWarning(
                    WarningCode.WINDOW_NOT_HOUR_ALIGNED,
                    f"Rule '{rule_id}' of hourly settled tariff '{tariff.id}' is not hour-aligned.",
                    {"tariff_id": tariff.id, "rule_id": rule_id},
                )
            )
    if capabilities is not None:
        needed = set(tariff.requires).union(*(rule.requires for rule in tariff.rules))
        for requirement in sorted(needed - set(capabilities)):
            found.append(
                EdibertWarning(
                    WarningCode.REQUIREMENT_UNMET,
                    f"Tariff '{tariff.id}' requires '{requirement}'.",
                    {"tariff_id": tariff.id, "requirement": requirement},
                )
            )
    return found


def check_grid_fee(grid_fee: GridFee) -> list[EdibertWarning]:
    """Warnings for rules and capacity charges that were left out of a resolved grid fee, non-convex capacity
    bands, and a capacity charge the house cannot supply the state for."""
    found: list[EdibertWarning] = []
    for skipped in grid_fee.skipped:
        if skipped.reason == SKIP_STATUS:
            code, params = WarningCode.GRID_RULE_SKIPPED_STATUS, {"rule_id": skipped.rule_id, "status": skipped.detail}
        elif skipped.reason == SKIP_NO_QUARTER_HOUR_METER:
            code, params = WarningCode.GRID_RULE_SKIPPED_NO_QUARTER_HOUR_METER, {"rule_id": skipped.rule_id}
        else:
            continue
        found.append(EdibertWarning(code, f"Grid rule '{skipped.rule_id}' skipped: {skipped.reason}.", params))
    found += check_capacity(grid_fee.capacity, grid_fee.capacity_skipped, grid_fee.area_id, grid_fee.quarter_hour_meter)
    return found
