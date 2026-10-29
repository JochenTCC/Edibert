"""Coded errors: stable ``code`` plus parameters, English message for logs.

The UI never shows ``str(error)`` to the user. It translates ``error.<code>`` via
:class:`edibert.i18n.Translator`, using ``error.params`` as placeholders.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable error codes. Every code needs ``error.<CODE>`` in all catalogs."""

    # Format / validation (``field`` is a path such as ``user_x.rules[night].effect.value``)
    TARIFF_UNKNOWN_FIELD = "TARIFF_UNKNOWN_FIELD"  # params: field
    RULE_UNKNOWN_FIELD = "RULE_UNKNOWN_FIELD"  # params: field, rule_id
    FIELD_MISSING = "FIELD_MISSING"  # params: field
    VALUE_INVALID = "VALUE_INVALID"  # params: field, value
    UNSUPPORTED_FEATURE = "UNSUPPORTED_FEATURE"  # params: feature, tariff_id
    RULE_VALUE_MISSING = "RULE_VALUE_MISSING"  # params: rule_id
    GRID_AREA_UNKNOWN = "GRID_AREA_UNKNOWN"  # params: area_id
    VAT_PERCENT_MISSING = "VAT_PERCENT_MISSING"  # params: tariff_id
    # Files and identifiers
    FILE_INVALID = "FILE_INVALID"  # params: path
    ID_COLLISION = "ID_COLLISION"  # params: tariff_id
    ID_PREFIX_MISSING = "ID_PREFIX_MISSING"  # params: tariff_id
    ID_PREFIX_RESERVED = "ID_PREFIX_RESERVED"  # params: tariff_id
    TARIFF_NOT_FOUND = "TARIFF_NOT_FOUND"  # params: tariff_id
    GRID_ID_COLLISION = "GRID_ID_COLLISION"  # params: grid_id
    GRID_ID_PREFIX_MISSING = "GRID_ID_PREFIX_MISSING"  # params: grid_id
    GRID_ID_PREFIX_RESERVED = "GRID_ID_PREFIX_RESERVED"  # params: grid_id
    # Tariff-format version track (``tariff_format`` root key)
    FORMAT_MISSING = "FORMAT_MISSING"  # params: path
    FORMAT_UNSUPPORTED = "FORMAT_UNSUPPORTED"  # params: path, value, supported
    MIGRATION_ANSWER_MISSING = "MIGRATION_ANSWER_MISSING"  # params: question_id
    # Evaluation
    PRICE_MISSING = "PRICE_MISSING"  # params: slot, tariff_id
    MARKET_PRICE_REQUIRED = "MARKET_PRICE_REQUIRED"  # params: slot, tariff_id
    HOLIDAY_REGION_MISSING = "HOLIDAY_REGION_MISSING"  # params: none
    HOLIDAY_REGION_UNKNOWN = "HOLIDAY_REGION_UNKNOWN"  # params: land, region
    CAPACITY_CHARGE_MISSING = "CAPACITY_CHARGE_MISSING"  # params: area_id, month
    CAPACITY_STATE_MISSING = "CAPACITY_STATE_MISSING"  # params: month
    CAPACITY_STATE_MONTH_MISMATCH = "CAPACITY_STATE_MONTH_MISMATCH"  # params: month, state_month
    # Market data and publishing
    MARKET_DATA_UNAVAILABLE = "MARKET_DATA_UNAVAILABLE"  # params: zone
    MARKET_ZONE_UNKNOWN = "MARKET_ZONE_UNKNOWN"  # params: land
    FORECASTER_UNAVAILABLE = "FORECASTER_UNAVAILABLE"  # params: name
    FORECAST_KEY_MISSING = "FORECAST_KEY_MISSING"  # params: env
    MQTT_LIBRARY_MISSING = "MQTT_LIBRARY_MISSING"  # params: none
    MQTT_CONNECTION_FAILED = "MQTT_CONNECTION_FAILED"  # params: host, port
    # Sharing with the free catalog (Catalog P6)
    CONTRIBUTION_INDIVIDUAL = "CONTRIBUTION_INDIVIDUAL"  # params: tariff_id
    CONTRIBUTION_TRANSPORT_OFF = "CONTRIBUTION_TRANSPORT_OFF"  # params: none


class EdibertError(Exception):
    """Error with a stable code and parameters.

    ``message`` is English and meant for logs and developers.
    """

    def __init__(self, code: ErrorCode, message: str, **params: Any) -> None:
        super().__init__(message)
        self.code = code
        self.params = params


class WarningCode(StrEnum):
    """Non-fatal findings. Every code needs ``warning.<CODE>`` in all catalogs."""

    WINDOW_NOT_HOUR_ALIGNED = "WINDOW_NOT_HOUR_ALIGNED"  # params: tariff_id, rule_id
    REQUIREMENT_UNMET = "REQUIREMENT_UNMET"  # params: tariff_id, requirement
    GRID_RULE_SKIPPED_STATUS = "GRID_RULE_SKIPPED_STATUS"  # params: rule_id, status
    GRID_RULE_SKIPPED_NO_QUARTER_HOUR_METER = "GRID_RULE_SKIPPED_NO_QUARTER_HOUR_METER"  # params: rule_id
    RULE_SHADOWED = "RULE_SHADOWED"  # params: rule_id, by
    RULE_NEVER_APPLIES = "RULE_NEVER_APPLIES"  # params: rule_id
    PRICE_UNUSUAL = "PRICE_UNUSUAL"  # params: value
    RULE_PRICE_UNUSUAL = "RULE_PRICE_UNUSUAL"  # params: rule_id, value
    SPOT_PRICES_GROSS = "SPOT_PRICES_GROSS"  # params: tariff_id
    MARKET_SOURCE_FAILED = "MARKET_SOURCE_FAILED"  # params: source, reason
    MARKET_DATA_INCOMPLETE = "MARKET_DATA_INCOMPLETE"  # params: zone, missing_from
    MARKET_CACHE_UNREADABLE = "MARKET_CACHE_UNREADABLE"  # params: path
    FORECAST_FAILED = "FORECAST_FAILED"  # params: name, reason
    MONTH_RATE_FALLBACK = "MONTH_RATE_FALLBACK"  # params: tariff_id, direction, month, used_month, rule
    MARKET_RANGE_INCOMPLETE = "MARKET_RANGE_INCOMPLETE"  # params: zone, missing_from, missing_slots
    GRID_CAPACITY_SKIPPED_STATUS = "GRID_CAPACITY_SKIPPED_STATUS"  # params: charge_id, status
    CAPACITY_BANDS_NOT_CONVEX = "CAPACITY_BANDS_NOT_CONVEX"  # params: charge_id
    CAPACITY_STATE_UNAVAILABLE = "CAPACITY_STATE_UNAVAILABLE"  # params: area_id
    # Sharing with the free catalog (Catalog P6)
    CONTRIBUTION_TRANSPORT_OFF = "CONTRIBUTION_TRANSPORT_OFF"  # params: none


@dataclass(frozen=True)
class EdibertWarning:
    """A finding that does not stop evaluation; the UI shows ``warning.<code>``."""

    code: WarningCode
    message: str  # English, for logs
    params: Mapping[str, Any] = field(default_factory=dict)
