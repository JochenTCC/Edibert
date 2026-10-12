"""Coded errors: stable ``code`` plus parameters, English message for logs.

The UI never shows ``str(error)`` to the user. It translates ``error.<code>`` via
:class:`edbert.i18n.Translator`, using ``error.params`` as placeholders.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    """Stable error codes. Every code needs ``error.<CODE>`` in all catalogs."""

    RULE_UNKNOWN_FIELD = "RULE_UNKNOWN_FIELD"  # params: field, rule_id
    UNSUPPORTED_FEATURE = "UNSUPPORTED_FEATURE"  # params: feature, tariff_id
    HOLIDAY_REGION_MISSING = "HOLIDAY_REGION_MISSING"  # params: none
    PRICE_MISSING = "PRICE_MISSING"  # params: slot, tariff_id
    ID_COLLISION = "ID_COLLISION"  # params: tariff_id


class EdbertError(Exception):
    """Error with a stable code and parameters.

    ``message`` is English and meant for logs and developers.
    """

    def __init__(self, code: ErrorCode, message: str, **params: Any) -> None:
        super().__init__(message)
        self.code = code
        self.params = params
