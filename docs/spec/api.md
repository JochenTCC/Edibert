# Library API (`edibert.api`)

Technical description of the public library facade for Earnie and other callers. Architecture: [architecture.md](architecture.md).

```python
from edibert import api
```

Only the names in `api.__all__` are covered by `api.API_VERSION` (currently `1`). A breaking change to one of them raises the version; additions do not. Everything else in the package may change without notice. The API imports neither `edibert.ui` nor `edibert.publish` (checked by `tests/test_api.py`).

## Functions

| Function | Purpose |
|---|---|
| `load_tariffs(catalog, user=None) -> TariffSet` | Catalog (`tariffs.json`) plus optional user file (`user_tariffs.json`). A missing user file means "no user tariffs"; a missing or unreadable catalog is `FILE_INVALID`. `TariffSet.origin[(direction, id)]` is `catalog` or `user`. Same ID in both files: `ID_COLLISION`; `user_` prefix rules: `ID_PREFIX_MISSING` / `ID_PREFIX_RESERVED`; unknown fields: `TARIFF_UNKNOWN_FIELD`. |
| `load_grid_fee_catalog(path) -> GridFeeCatalog` | `grid_fees.json`: `areas` by ID and `rule_sets`. |
| `parse_grid_fee_config(raw) -> GridFeeConfig` | The `netznutzung` object of a house profile. |
| `resolve_grid_fee(config, catalog=None) -> GridFee` | Profile field plus catalog area to an evaluable grid fee; unknown area: `GRID_AREA_UNKNOWN`. |
| `pricing_context(timezone, land=None, region=None) -> PricingContext` | Time zone and holiday location of one house profile. The region is checked up front: unknown country/region is `HOLIDAY_REGION_UNKNOWN`, a region without `land` is `FIELD_MISSING`. Without a region the context works; a holiday rule then fails with `HOLIDAY_REGION_MISSING`. |
| `tariff_price_series(tariff, ctx, start, end, *, resolution_min=15, market=None, forecast_from=None, grid_fee=None, capabilities=None) -> PriceSeries` | Prices for `[start, end)` at 15, 30 or 60 minutes. |
| `evaluate(tariff, slot_start, ctx, epex_cent=None, grid_fee=None) -> PriceResult` / `price_cent(...) -> float` | One slot, with or without the intermediate steps. |
| `builtin_forecaster(method, tz) -> Forecaster` | The free methods `mirror` and `hold`; anything else is `VALUE_INVALID`. |

## Forecasters

The library takes a forecaster **object** implementing `Forecaster.forecast(known, start, end) -> {slot_start_utc: cent/kWh}`. A caller hands in its own model directly (Earnie: OLS model), no key involved. Plug-ins loaded from the entry-point group `edibert.forecasters` and their key (`EDIBERT_FORECAST_KEY`) belong to the product layer (`edibert.publish.forecasters`), not to the library.

## Types and constants

`TariffSet`, `Tariff`, `PriceResult`, `PricePoint`, `PriceSeries`, `PricingContext`, `GridArea`, `GridFee`, `GridFeeCatalog`, `GridFeeConfig`, `HoldLastForecaster`, `MirrorForecaster`; `IMPORT`, `EXPORT`, `RESOLUTIONS`, `USER_PREFIX`.

## Errors and warnings

`EdibertError` (`code: ErrorCode`, `params`) and `EdibertWarning` (`code: WarningCode`, `params`). Callers branch on the code, never on the English message.

## Not yet in the API

* Tariff-format version (`tariff_format` root key) and migrations (`plan_migration` / `migrate`): open, see the Earnie config-migration draft §3.7.
* Monthly-table fallback with `MONTH_RATE_FALLBACK`, `market_cent` and method per point, range queries for market prices: `0.1.g`.
