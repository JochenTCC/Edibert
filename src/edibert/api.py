"""Public library API of Edibert for Earnie and other callers (``from edibert import api``).

Only the names in ``__all__`` are covered by ``API_VERSION``; everything else in the package may change
without notice. A breaking change to a name here raises ``API_VERSION``; additions do not.

The API knows neither the editor UI nor the MQTT publisher. All problems are coded
:class:`EdibertError` (``code`` plus ``params``) or :class:`EdibertWarning`; nothing is skipped silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from edibert import gridfee as _gridfee
from edibert import store as _store
from edibert._fields import missing
from edibert.context import HolidayCalendar, PricingContext
from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.fileformat import TARIFF_FORMAT, TARIFF_TRACK_FILES
from edibert.gridfee import (
    GridArea,
    GridFee,
    GridFeeCatalog,
    GridFeeConfig,
    flat_user_grid_area,
    parse_grid_fee_config,
    resolve_grid_fee,
)
from edibert.market.forecast import (
    Forecaster,
    HoldLastForecaster,
    MirrorForecaster,
    builtin_forecaster,
)
from edibert.migration import (
    STANDARD_VAT_PERCENT,
    MigrationBlocker,
    MigrationPlan,
    MigrationQuestion,
    MigrationResult,
    migrate,
    plan_migration,
)
from edibert.series import RESOLUTIONS, PricePoint, PriceSeries, tariff_price_series
from edibert.store import USER_PREFIX, TariffSet
from edibert.tariff import EXPORT, IMPORT, PriceResult, Tariff, evaluate, price_cent

API_VERSION = 2  # raised on a breaking change to a name in __all__ (2: tariff_format, area_id required)

__all__ = [
    "API_VERSION",
    "EXPORT",
    "IMPORT",
    "RESOLUTIONS",
    "STANDARD_VAT_PERCENT",
    "TARIFF_FORMAT",
    "TARIFF_TRACK_FILES",
    "USER_PREFIX",
    "EdibertError",
    "EdibertWarning",
    "ErrorCode",
    "Forecaster",
    "GridArea",
    "GridFee",
    "GridFeeCatalog",
    "GridFeeConfig",
    "HoldLastForecaster",
    "MigrationBlocker",
    "MigrationPlan",
    "MigrationQuestion",
    "MigrationResult",
    "MirrorForecaster",
    "PricePoint",
    "PriceResult",
    "PriceSeries",
    "PricingContext",
    "Tariff",
    "TariffSet",
    "WarningCode",
    "builtin_forecaster",
    "evaluate",
    "flat_user_grid_area",
    "load_grid_fee_catalog",
    "load_grid_fees",
    "load_tariffs",
    "migrate",
    "parse_grid_fee_config",
    "plan_migration",
    "price_cent",
    "pricing_context",
    "resolve_grid_fee",
    "save_user_grid_area",
    "tariff_price_series",
]


def load_tariffs(catalog: Path | None, user: Path | None = None) -> TariffSet:
    """The catalog (``tariffs.json``) and the optional user file (``user_tariffs.json``) as one set.

    A missing user file is no error (no user tariffs yet); a missing catalog file is. Every tariff keeps
    its origin (``TariffSet.origin[(direction, id)]`` is ``catalog`` or ``user``). The same ID in both
    files, a wrong ID prefix or an unknown field is a coded error. Both files need ``tariff_format``
    (``FORMAT_MISSING`` / ``FORMAT_UNSUPPORTED``); a gross tariff without ``vat_percent`` is ``VAT_PERCENT_MISSING``.
    """
    return _store.load_tariffs(catalog, user)


def load_grid_fee_catalog(path: Path) -> GridFeeCatalog:
    """The grid-fee catalog (``grid_fees.json``) alone: areas by ID and rule sets."""
    return _gridfee.load_grid_fee_catalog(path)


def load_grid_fees(catalog: Path | None, user: Path | None = None) -> GridFeeCatalog:
    """Catalog (``grid_fees.json``) and optional user file (``user_grid_fees.json``) as one view.

    A missing user file means no user areas. ``GridFeeCatalog.origin[area_id]`` is ``catalog`` or ``user``.
    User IDs (areas and rule sets) start with ``user_``, catalog IDs must not (``GRID_ID_PREFIX_*``); an ID
    twice is ``GRID_ID_COLLISION``.
    """
    return _gridfee.load_grid_fees(catalog, user)


def save_user_grid_area(path: Path, area: Mapping[str, Any]) -> None:
    """Add or replace one area (same ID) in ``user_grid_fees.json``; the file is created if missing.

    ``area`` has the shape of an entry in ``areas`` (see :func:`flat_user_grid_area` for an own flat work
    price). The whole file is validated first; on any error it stays unchanged.
    """
    _gridfee.save_user_grid_area(path, area)


def pricing_context(timezone: str, land: str | None = None, region: str | None = None) -> PricingContext:
    """Pricing context of one house profile, checked up front.

    ``region`` (e.g. ``"9"`` for Vienna, ``"BY"`` for Bavaria) selects the holiday calendar and needs
    ``land``. An unknown country/region is ``HOLIDAY_REGION_UNKNOWN`` here, not at the first holiday
    rule. Without a region the context still works; holiday rules then fail with
    ``HOLIDAY_REGION_MISSING``.
    """
    if region and not land:
        raise missing("land")
    ctx = PricingContext(timezone, land, region)
    if ctx.land and ctx.region:
        HolidayCalendar(ctx.land, ctx.region)
    return ctx
