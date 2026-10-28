"""JSON Schema of a single tariff entry, generated from the field tables of the parser.

The schema is for editors and external tools. The parser stays the single source of
truth; ``tests/test_schema.py`` checks that both agree on field names and on the examples.
"""

from __future__ import annotations

from typing import Any

from edibert.rules import HOLIDAY_MODES, MODES, REQUIRES, RULE_FIELDS
from edibert.tariff import EXPORT_TYPES, IMPORT_TYPES, TARIFF_FIELDS

_NUMBER: dict[str, Any] = {"type": "number"}
_NON_NEGATIVE: dict[str, Any] = {"type": "number", "minimum": 0}
_DATE: dict[str, Any] = {"type": "string", "format": "date"}
_TEXT: dict[str, Any] = {"type": "string", "minLength": 1}
_TIME: dict[str, Any] = {"type": "string", "pattern": r"^([01]?\d|2[0-3]):[0-5]\d$|^24:00$"}
_WEEKDAY_ITEM: dict[str, Any] = {
    "oneOf": [
        {"type": "integer", "minimum": 0, "maximum": 6},
        {"enum": ["mon", "tue", "wed", "thu", "fri", "sat", "sun", "weekday", "weekend", "holiday"]},
    ]
}


def _rule_schema() -> dict[str, Any]:
    properties: dict[str, Any] = {
        "$comment": {"type": "string"},
        "id": _TEXT,
        "label": _TEXT,
        "valid_from": _DATE,
        "valid_to": _DATE,
        "months": {"type": "array", "minItems": 1, "items": {"type": "integer", "minimum": 1, "maximum": 12}},
        "weekdays": {"oneOf": [_WEEKDAY_ITEM, {"type": "array", "minItems": 1, "items": _WEEKDAY_ITEM}]},
        "time": {
            "type": "object",
            "required": ["from", "to"],
            "additionalProperties": False,
            "properties": {"from": _TIME, "to": _TIME},
        },
        "effect": {
            "type": "object",
            "required": ["mode", "value"],
            "additionalProperties": False,
            "properties": {"mode": {"enum": list(MODES)}, "value": _NUMBER},
        },
        "when_market_cent_kwh": {
            "type": "object",
            "minProperties": 1,
            "maxProperties": 1,
            "additionalProperties": False,
            "properties": {"below": _NUMBER, "above": _NUMBER},
        },
        "requires": {"type": "array", "items": {"enum": list(REQUIRES)}},
    }
    return {
        "type": "object",
        "required": ["id", "effect"],
        "additionalProperties": False,
        "properties": properties,
    }


def _tariff_properties() -> dict[str, Any]:
    return {
        "$comment": {"type": "string"},
        "id": _TEXT,
        "label": _TEXT,
        "type": {"enum": sorted(set(IMPORT_TYPES) | set(EXPORT_TYPES))},
        "land": {"enum": ["AT", "DE", "CH"]},
        "regions": {"type": "array", "minItems": 1, "uniqueItems": True, "items": _TEXT},
        "currency": {"enum": ["EUR", "CHF"]},
        "supplier_id": _TEXT,
        "notes": {"type": "string"},
        "settlement_fee_cent_kwh": _NUMBER,
        "markup_percent": _NUMBER,
        "prices_include_vat": {"type": "boolean"},
        "vat_percent": _NON_NEGATIVE,
        "settlement_mtu": {"enum": ["15min", "60min"]},
        "fix_cent_kwh": _NUMBER,
        "k_push_cent": _NUMBER,
        "monthly_rates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["year", "month", "tariff_cent_kwh"],
                "additionalProperties": False,
                "properties": {
                    "year": {"type": "integer"},
                    "month": {"type": "integer", "minimum": 1, "maximum": 12},
                    "tariff_cent_kwh": _NUMBER,
                },
            },
        },
        "monthly_seed": {"type": "object"},
        "feed_in_fee_factor": _NON_NEGATIVE,
        "feed_in_fix_cent": _NUMBER,
        "rules": {"type": "array", "items": _rule_schema()},
        "price_floor_cent_kwh": _NUMBER,
        "price_cap_cent_kwh": _NUMBER,
        "requires": {"type": "array", "items": {"enum": list(REQUIRES)}},
        "behavior_notes": {"type": "string"},
        "source": {"type": "string"},
        "last_verified": _DATE,
        "holidays": {
            "type": "object",
            "additionalProperties": False,
            "properties": {"treat_as": {"enum": list(HOLIDAY_MODES)}},
        },
        "extra_holiday_dates": {"type": "array", "items": _DATE},
        "individual": {"type": "boolean"},
        "applies_to": {"const": "main"},
        "monthly_fee_eur": _NON_NEGATIVE,
        "grid_monthly_fee_eur": _NON_NEGATIVE,
        "metering_monthly_fee_eur": _NON_NEGATIVE,
        "other_monthly_fee_eur": _NON_NEGATIVE,
    }


def tariff_schema() -> dict[str, Any]:
    """JSON Schema (draft 2020-12) for one tariff entry."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Edibert tariff",
        "type": "object",
        "required": ["id", "type", "supplier_id", "vat_percent"],
        "additionalProperties": False,
        "properties": _tariff_properties(),
    }


def tariff_field_names() -> tuple[str, ...]:
    """Fields the parser accepts (used by the consistency test)."""
    return TARIFF_FIELDS


def rule_field_names() -> tuple[str, ...]:
    return RULE_FIELDS
