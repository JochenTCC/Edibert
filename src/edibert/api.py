"""Public library API of Edibert for Earnie and other callers (``from edibert import api``).

Only the names in ``__all__`` are covered by ``API_VERSION``; everything else in the package may change
without notice. A breaking change to a name here raises ``API_VERSION``; additions do not.

The API knows neither the editor UI nor the MQTT publisher. All problems are coded
:class:`EdibertError` (``code`` plus ``params``) or :class:`EdibertWarning`; nothing is skipped silently.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from edibert import gridfee as _gridfee
from edibert import store as _store
from edibert._fields import invalid, missing
from edibert.capacity import (
    CapacityBand,
    CapacityCharge,
    CapacityLadder,
    CapacityState,
    LadderRung,
    capacity_charge_eur,
    capacity_ladder,
    charge_for_month,
    parse_capacity_state,
)
from edibert.catalog_import import (
    KEEP_LOCAL,
    TAKE_PACKAGE,
    EntryChange,
    ImportPlan,
    MonthConflict,
    apply_package_import,
    plan_package_import,
    write_catalog_pair,
)
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
from edibert.identity import (
    differs_from_db,
    grid_area_identity,
    grid_area_version,
    tariff_identity,
    tariff_version,
)
from edibert.market.archive import MarketArchive, MarketRange, known_at, market_range
from edibert.market.forecast import (
    METHOD_HOLD,
    METHOD_MIRROR,
    Forecaster,
    HoldLastForecaster,
    MirrorForecaster,
    builtin_forecaster,
)
from edibert.market.service import MarketData, MarketService
from edibert.market.sources import ZONE_BY_LAND, HttpGet, http_get, zone_for_land
from edibert.market.sources import SourceError as MarketSourceError
from edibert.migration import (
    STANDARD_VAT_PERCENT,
    MigrationBlocker,
    MigrationPlan,
    MigrationQuestion,
    MigrationResult,
    migrate,
    plan_migration,
)
from edibert.package import (
    CatalogPackage,
    PackageManifest,
    read_package,
    verify_package,
)
from edibert.series import (
    METHOD_EXACT,
    RESOLUTIONS,
    PricePoint,
    PriceSeries,
    tariff_price_series,
)
from edibert.store import USER_PREFIX, TariffSet
from edibert.tariff import (
    EXPORT,
    FALLBACK_PRIOR_MONTH,
    FALLBACK_PRIOR_YEAR,
    IMPORT,
    DbRef,
    PriceResult,
    Tariff,
    evaluate,
    parse_tariff,
    price_cent,
    version_at,
)

API_VERSION = 2  # raised on a breaking change to a name in __all__ (2: tariff_format, area_id required)

__all__ = [
    "API_VERSION",
    "EXPORT",
    "FALLBACK_PRIOR_MONTH",
    "FALLBACK_PRIOR_YEAR",
    "IMPORT",
    "KEEP_LOCAL",
    "METHOD_EXACT",
    "METHOD_HOLD",
    "METHOD_MIRROR",
    "RESOLUTIONS",
    "STANDARD_VAT_PERCENT",
    "TAKE_PACKAGE",
    "TARIFF_FORMAT",
    "TARIFF_TRACK_FILES",
    "USER_PREFIX",
    "CapacityBand",
    "CapacityCharge",
    "CapacityLadder",
    "CapacityState",
    "CatalogPackage",
    "DbRef",
    "EdibertError",
    "EdibertWarning",
    "EntryChange",
    "ErrorCode",
    "Forecaster",
    "GridArea",
    "GridFee",
    "GridFeeCatalog",
    "GridFeeConfig",
    "HoldLastForecaster",
    "ImportPlan",
    "LadderRung",
    "MarketArchive",
    "MarketData",
    "MarketRange",
    "MarketSourceError",
    "MigrationBlocker",
    "MigrationPlan",
    "MigrationQuestion",
    "MigrationResult",
    "MirrorForecaster",
    "MonthConflict",
    "PackageManifest",
    "PricePoint",
    "PriceResult",
    "PriceSeries",
    "PricingContext",
    "Tariff",
    "TariffSet",
    "WarningCode",
    "apply_package_import",
    "builtin_forecaster",
    "capacity_charge_eur",
    "capacity_ladder",
    "charge_for_month",
    "differs_from_db",
    "evaluate",
    "flat_user_grid_area",
    "grid_area_identity",
    "grid_area_version",
    "known_at",
    "load_grid_fee_catalog",
    "load_grid_fees",
    "load_tariffs",
    "market_live",
    "market_range",
    "market_zone",
    "migrate",
    "parse_capacity_state",
    "parse_grid_fee_config",
    "parse_tariff",
    "plan_migration",
    "plan_package_import",
    "price_cent",
    "pricing_context",
    "read_package",
    "resolve_grid_fee",
    "save_user_grid_area",
    "tariff_identity",
    "tariff_price_series",
    "tariff_version",
    "verify_package",
    "version_at",
    "write_catalog_pair",
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


def market_zone(land: str) -> str:
    """Bidding zone of a country for the market prices (``AT`` -> ``AT``, ``DE`` -> ``DE-LU``, ``CH`` -> ``CH``).

    Any other country is ``MARKET_ZONE_UNKNOWN``.
    """
    return zone_for_land(land)


def market_live(
    zone: str,
    data_dir: Path,
    tz: ZoneInfo,
    *,
    entsoe_token: str = "",
    get: HttpGet | None = None,
    history_days: int = 0,
    timeout: float = 30,
    now: datetime | None = None,
) -> MarketData:
    """Day-ahead prices of ``zone`` for today and, from the 12:00 publish on, tomorrow (live operation).

    Chain: cache under ``data_dir`` -> ENTSO-E (only with ``entsoe_token``) -> Energy-Charts -> aWATTar
    (AT and DE-LU only). ``history_days`` (0 to 7) adds that many local days before today to the expected
    window, e.g. as mirror sources for a forecaster. ``get`` replaces the HTTP call for every source (a
    caller's own transport, recording or replay); it raises :class:`MarketSourceError` when a source fails,
    so the chain notes it and asks the next source (any other exception ends the call). A partial answer is ``MarketData.complete == False``
    with ``MARKET_DATA_INCOMPLETE``; no price at all is ``MARKET_DATA_UNAVAILABLE``.
    """
    if zone not in ZONE_BY_LAND.values():
        raise invalid("zone", zone)
    service = MarketService(
        zone, Path(data_dir), entsoe_token=entsoe_token, get=get or http_get, timeout=timeout, history_days=history_days
    )
    return service.load(tz, now)


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
