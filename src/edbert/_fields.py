"""Small strict readers for JSON fields. All problems are coded :class:`EdbertError`."""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from datetime import date
from typing import Any

from edbert.errors import EdbertError, ErrorCode


def invalid(path: str, value: object) -> EdbertError:
    return EdbertError(
        ErrorCode.VALUE_INVALID, f"Invalid value {value!r} for field '{path}'.", field=path, value=value
    )


def missing(path: str) -> EdbertError:
    return EdbertError(ErrorCode.FIELD_MISSING, f"Required field '{path}' is missing.", field=path)


def as_dict(raw: object, path: str) -> Mapping[str, Any]:
    if not isinstance(raw, dict):
        raise invalid(path, raw)
    return raw


def check_known(
    raw: Mapping[str, Any],
    allowed: Collection[str],
    path: str,
    code: ErrorCode = ErrorCode.TARIFF_UNKNOWN_FIELD,
    **extra: object,
) -> None:
    """Reject unknown fields. ``$comment`` is allowed everywhere and ignored."""
    for key in raw:
        if key != "$comment" and key not in allowed:
            full = f"{path}.{key}"
            raise EdbertError(code, f"Unknown field '{full}'.", field=full, **extra)


def get_str(raw: Mapping[str, Any], key: str, path: str, *, required: bool = False) -> str | None:
    value = raw.get(key)
    if value is None:
        if required:
            raise missing(f"{path}.{key}")
        return None
    if not isinstance(value, str) or not value.strip():
        raise invalid(f"{path}.{key}", value)
    return value.strip()


def get_number(
    raw: Mapping[str, Any],
    key: str,
    path: str,
    *,
    required: bool = False,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    value = raw.get(key)
    if value is None:
        if required:
            raise missing(f"{path}.{key}")
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise invalid(f"{path}.{key}", value)
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise invalid(f"{path}.{key}", value)
    return float(value)


def get_bool(raw: Mapping[str, Any], key: str, path: str, default: bool) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise invalid(f"{path}.{key}", value)
    return value


def parse_date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise invalid(path, value)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise invalid(path, value) from exc


def get_date(raw: Mapping[str, Any], key: str, path: str) -> date | None:
    value = raw.get(key)
    return None if value is None else parse_date(value, f"{path}.{key}")


def get_choice_list(raw: Mapping[str, Any], key: str, path: str, allowed: Collection[str]) -> tuple[str, ...]:
    value = raw.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise invalid(f"{path}.{key}", value)
    for item in value:
        if item not in allowed:
            raise invalid(f"{path}.{key}", item)
    return tuple(value)
