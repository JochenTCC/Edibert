"""Public library API of Edibert for Earnie and other callers (``from edibert import api``).

Only the names in ``__all__`` are covered by ``API_VERSION``; everything else in the package may change
without notice. A breaking change to a name here raises ``API_VERSION``; additions do not.

The API knows neither the editor UI nor the MQTT publisher. All problems are coded
:class:`EdibertError` (``code`` plus ``params``) or :class:`EdibertWarning`; nothing is skipped silently.
"""

from __future__ import annotations

from pathlib import Path

from edibert import gridfee as _gridfee
from edibert import store as _store
from edibert._fields import missing
from edibert.context import HolidayCalendar, PricingContext
from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.gridfee import (
    GridArea,
    GridFee,
    GridFeeCatalog,
    GridFeeConfig,
    parse_grid_fee_config,
    resolve_grid_fee,
)
from edibert.market.forecast import (
    Forecaster,
    HoldLastForecaster,
    MirrorForecaster,
    builtin_forecaster,
)
from edibert.series import RESOLUTIONS, PricePoint, PriceSeries, tariff_price_series
from edibert.store import USER_PREFIX, TariffSet
from edibert.tariff import EXPORT, IMPORT, PriceResult, Tariff, evaluate, price_cent

API_VERSION = 1  # raised on a breaking change to a name in __all__

__all__ = [
    "API_VERSION",
    "EXPORT",
    "IMPORT",
    "RESOLUTIONS",
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
    "load_grid_fee_catalog",
    "load_tariffs",
    "parse_grid_fee_config",
    "price_cent",
    "pricing_context",
    "resolve_grid_fee",
    "tariff_price_series",
]


def load_tariffs(catalog: Path | None, user: Path | None = None) -> TariffSet:
    """The catalog (``tariffs.json``) and the optional user file (``user_tariffs.json``) as one set.

    A missing user file is no error (no user tariffs yet); a missing catalog file is. Every tariff keeps
    its origin (``TariffSet.origin[(direction, id)]`` is ``catalog`` or ``user``). The same ID in both
    files, a wrong ID prefix or an unknown field is a coded error.
    """
    return _store.load_tariffs(catalog, user)


def load_grid_fee_catalog(path: Path) -> GridFeeCatalog:
    """The grid-fee catalog (``grid_fees.json``): areas by ID and rule sets."""
    return _gridfee.load_grid_fee_catalog(path)


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
