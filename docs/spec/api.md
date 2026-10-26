# Library API (`edibert.api`)

Technical description of the public library facade for Earnie and other callers. Architecture: [architecture.md](architecture.md).

```python
from edibert import api
```

Only the names in `api.__all__` are covered by `api.API_VERSION` (currently `2`; raised from `1` by `0.1.i`: required `tariff_format`, required `netznutzung.area_id`, `GridFeeConfig` / `GridFee` without own values, `resolve_grid_fee` needs the area view, every tariff needs `vat_percent`). A breaking change to one of them raises the version; additions do not. Everything else in the package may change without notice. The API imports neither `edibert.ui` nor `edibert.publish` (checked by `tests/test_api.py`).

## Functions

| Function | Purpose |
|---|---|
| `load_tariffs(catalog, user=None) -> TariffSet` | Catalog (`tariffs.json`) plus optional user file (`user_tariffs.json`). A missing user file means "no user tariffs"; a missing or unreadable catalog is `FILE_INVALID`. `TariffSet.origin[(direction, id)]` is `catalog` or `user`. Same ID in both files: `ID_COLLISION`; `user_` prefix rules: `ID_PREFIX_MISSING` / `ID_PREFIX_RESERVED`; unknown fields: `TARIFF_UNKNOWN_FIELD`; no or unknown `tariff_format`: `FORMAT_MISSING` / `FORMAT_UNSUPPORTED`; tariff without `vat_percent` (gross or net): `VAT_PERCENT_MISSING`. |
| `load_grid_fee_catalog(path) -> GridFeeCatalog` | `grid_fees.json` alone: `areas` by ID and `rule_sets`, every area with origin `catalog`. |
| `load_grid_fees(catalog, user=None) -> GridFeeCatalog` | Catalog plus optional user file (`user_grid_fees.json`) as one view; `GridFeeCatalog.origin[area_id]` is `catalog` or `user`. A missing user file means "no user areas". `user_` prefix rules for areas and rule sets: `GRID_ID_PREFIX_MISSING` / `GRID_ID_PREFIX_RESERVED`; an ID twice: `GRID_ID_COLLISION`; format key as for tariffs. |
| `save_user_grid_area(path, area) -> None` | Adds or replaces (same ID) one area in `user_grid_fees.json`; creates the file with the current `tariff_format` if missing. The whole file is validated first; on any error (bad area, unmigrated file) it stays unchanged. Earnie's house-profile UI writes the own work price through it. |
| `flat_user_grid_area(area_id, base_cent_kwh, *, label=None, land=None) -> dict` | An area object with the same work price for both metering types and no rule set (an own flat grid fee), ready for `save_user_grid_area` or the migration. |
| `parse_grid_fee_config(raw) -> GridFeeConfig` | The `netznutzung` object of a house profile: `area_id` (required, `FIELD_MISSING`), `power_metering`, `quarter_hour_meter`, `include_status`; anything else is `TARIFF_UNKNOWN_FIELD`. |
| `resolve_grid_fee(config, catalog) -> GridFee` | Profile field plus the area view (from `load_grid_fees`) to an evaluable grid fee; unknown area: `GRID_AREA_UNKNOWN`. |
| `pricing_context(timezone, land=None, region=None) -> PricingContext` | Time zone and holiday location of one house profile. The region is checked up front: unknown country/region is `HOLIDAY_REGION_UNKNOWN`, a region without `land` is `FIELD_MISSING`. Without a region the context works; a holiday rule then fails with `HOLIDAY_REGION_MISSING`. |
| `tariff_price_series(tariff, ctx, start, end, *, resolution_min=15, market=None, forecast_from=None, grid_fee=None, capabilities=None) -> PriceSeries` | Prices for `[start, end)` at 15, 30 or 60 minutes. |
| `parse_tariff(raw, direction) -> Tariff` | One tariff object (`direction` = `IMPORT` / `EXPORT`), checked exactly like an entry of a tariff file (unknown fields, type fields, `vat_percent`, …), but without the `user_` prefix rule and without `tariff_format`: both belong to files. For tariffs a caller builds itself (Earnie: the scenario shortcut *Eigener Festpreis*). |
| `evaluate(tariff, slot_start, ctx, epex_cent=None, grid_fee=None) -> PriceResult` / `price_cent(...) -> float` | One slot, with or without the intermediate steps. |
| `builtin_forecaster(method, tz) -> Forecaster` | The free methods `mirror` and `hold`; anything else is `VALUE_INVALID`. |
| `plan_migration(docs, *, user_grid_areas=()) -> MigrationPlan` | What `migrate` would change; see below. |
| `migrate(docs, answers=None, *, user_grid_areas=()) -> MigrationResult` | Brings the tariff-track files to the current `tariff_format`; see below. |

## Migration of the tariff-track files

Pure functions: the caller reads the files, passes them as `docs = {file name: document}` (names from `TARIFF_TRACK_FILES`; a missing file is left out or `None`, any other name is `VALUE_INVALID`), and writes the returned documents itself with its own backup. What the step does is described in [tariff-format.md](tariff-format.md) section 2a.

* `user_grid_areas`: area objects (shape of an entry in `areas`, IDs `user_…`) to create in `user_grid_fees.json`; build an own flat price with `flat_user_grid_area`. Earnie passes one per house profile it moves off `area_id: null`.
* `MigrationPlan`: `current` (`tariff_format` per given file, `None` = untagged), `to_format`, `changed_files` (what `migrate` writes, assuming the questions get answered), `questions`, `blockers`, and the properties `needed` (anything to do) and `can_run` (no blockers).
* `MigrationQuestion`: `id` (key of the answer, e.g. `vat_percent:import:user_x`), `code` (`VAT_PERCENT`, UI text `question.VAT_PERCENT`), `file`, `kind` (`number`), `required` (`True`), `default` (prefill from `STANDARD_VAT_PERCENT` by the tariff's `land`, or `None`), `params` (`tariff_id`, `label`, `direction`, `prices` = `gross` / `net`, `land`). Asked for every user tariff without a rate, gross or net.
* `MigrationBlocker`: `code` (an `ErrorCode`, UI text `error.<code>`), `file`, `params`, `message` (English, for logs). Blockers: `FORMAT_UNSUPPORTED`, `GRID_ID_COLLISION` (a user area exists with other values), and the first load error per file of the migrated documents (e.g. `VAT_PERCENT_MISSING` in the catalog, `GRID_ID_PREFIX_MISSING` for a handed-in area).
* `MigrationResult`: `docs` (all given files after the step, plus a created `user_grid_fees.json`), `changed_files`, `blockers`. With blockers nothing changes: `docs` are copies of the input and `changed_files` is empty.
* `answers`: `{question id: value}`; a VAT answer is a number `>= 0`. A required question without an answer is `MIGRATION_ANSWER_MISSING`, an invalid answer `VALUE_INVALID` (both raised). Running `migrate` on migrated files changes nothing.

For Earnie's `MigrationStep` (`runtime_store/migration/types.py`): `detect` is `plan.needed`, the questions map to `Question` (`id`, `required`; `kind` `number` and `default` are new there), blockers to `Blocker` with the German text from `error.<code>`, and `StepResult(docs, changed_files, blockers)` comes from `MigrationResult`.

## Forecasters

The library takes a forecaster **object** implementing `Forecaster.forecast(known, start, end) -> {slot_start_utc: cent/kWh}`. A caller hands in its own model directly (Earnie: OLS model), no key involved. Plug-ins loaded from the entry-point group `edibert.forecasters` and their key (`EDIBERT_FORECAST_KEY`) belong to the product layer (`edibert.publish.forecasters`), not to the library.

## Types and constants

`TariffSet`, `Tariff`, `PriceResult`, `PricePoint`, `PriceSeries`, `PricingContext`, `GridArea`, `GridFee`, `GridFeeCatalog`, `GridFeeConfig`, `HoldLastForecaster`, `MirrorForecaster`, `MigrationPlan`, `MigrationQuestion`, `MigrationBlocker`, `MigrationResult`; `IMPORT`, `EXPORT`, `RESOLUTIONS`, `USER_PREFIX`, `TARIFF_FORMAT` (current version, `1`), `TARIFF_TRACK_FILES`, `STANDARD_VAT_PERCENT` (`{"AT": 20.0, "DE": 19.0, "CH": 8.1}`, prefill only).

## Errors and warnings

`EdibertError` (`code: ErrorCode`, `params`) and `EdibertWarning` (`code: WarningCode`, `params`). Callers branch on the code, never on the English message.

## Not yet in the API

* Monthly-table fallback with `MONTH_RATE_FALLBACK`, `market_cent` and method per point, range queries for market prices: `0.1.g`.
