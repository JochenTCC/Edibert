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
| `resolve_grid_fee(config, catalog) -> GridFee` | Profile field plus the area view (from `load_grid_fees`) to an evaluable grid fee; unknown area: `GRID_AREA_UNKNOWN`. `GridFee.capacity` holds the capacity charges in effect after `include_status`, `capacity_skipped` the left-out ones (ID to status). |
| `charge_for_month(charges, month, area_id) -> CapacityCharge \| None` | The capacity charge that covers the calendar month of `month` ([tariff-format.md](tariff-format.md) section 5b); `None` before the first entry starts; a later uncovered month is `CAPACITY_CHARGE_MISSING`. |
| `capacity_charge_eur(charge, peak_kw) -> float` | Net month amount for a month peak (minimum and bands applied), EUR rounded to cents. |
| `capacity_ladder(charge, state, month, ctx, *, step_kw=None, max_kw=None, require_state=False) -> CapacityLadder` | Remaining cost of the month by peak, relative to the measured `CapacityState` (sunk cost 0) or absolute without one; `CAPACITY_STATE_MONTH_MISMATCH`, `CAPACITY_STATE_MISSING`. `CapacityLadder.to_dict()` has the shape of one entry of the series' capacity block. |
| `parse_capacity_state(raw) -> CapacityState` | `{peak_15min_kw, as_of}` from JSON; `as_of` ISO 8601, naive = local time. |
| `pricing_context(timezone, land=None, region=None) -> PricingContext` | Time zone and holiday location of one house profile. The region is checked up front: unknown country/region is `HOLIDAY_REGION_UNKNOWN`, a region without `land` is `FIELD_MISSING`. Without a region the context works; a holiday rule then fails with `HOLIDAY_REGION_MISSING`. |
| `tariff_price_series(tariff, ctx, start, end, *, resolution_min=15, market=None, forecast_from=None, grid_fee=None, capabilities=None, forecast_method=None, capacity_state=None) -> PriceSeries` | Prices for `[start, end)` at 15, 30 or 60 minutes ([tariff-format.md](tariff-format.md) section 8). Every `PricePoint` carries `market_cent` and `method` (see below). A `monthly_table` month taken from another month is in `PriceSeries.warnings` as `MONTH_RATE_FALLBACK`, once per requested month. With a capacity charge in the grid fee, `PriceSeries.capacity` (and the `capacity` key of `to_dict()`) holds one ladder per month; `capacity_state` is the measured month-to-date peak. |
| `parse_tariff(raw, direction) -> Tariff` | One tariff object (`direction` = `IMPORT` / `EXPORT`), checked exactly like an entry of a tariff file (unknown fields, type fields, `vat_percent`, …), but without the `user_` prefix rule and without `tariff_format`: both belong to files. For tariffs a caller builds itself (Earnie: the scenario shortcut *Eigener Festpreis*). |
| `evaluate(tariff, slot_start, ctx, epex_cent=None, grid_fee=None) -> PriceResult` / `price_cent(...) -> float` | One slot, with or without the intermediate steps. `PriceResult.warnings` holds `MONTH_RATE_FALLBACK` when the monthly rate came from another month (`price_cent` drops it; use `evaluate` or the series when the fallback matters). |
| `market_zone(land) -> str` | Bidding zone of a country: `AT` → `AT`, `DE` → `DE-LU`, `CH` → `CH`; anything else is `MARKET_ZONE_UNKNOWN`. |
| `market_live(zone, data_dir, tz, *, entsoe_token="", get=None, history_days=0, timeout=30, now=None) -> MarketData` | Day-ahead prices for live operation: today and, from the 12:00 publish on, tomorrow, plus `history_days` lead days; see below. |
| `market_range(zone, start, end, cache_dir) -> MarketRange` | Day-ahead prices for any range (simulation, backtesting); shorthand for `MarketArchive(zone, cache_dir).prices(start, end)`, see below. |
| `known_at(prices, moment, tz) -> dict` | The prices a caller could know at `moment` (backtesting): up to 12:00 local time they end with today, from 12:00 with tomorrow (Earnie's `build_market_data_as_of`). `moment` must be aware. |
| `builtin_forecaster(method, tz) -> Forecaster` | The free methods `mirror` and `hold`; anything else is `VALUE_INVALID`. |
| `tariff_identity(raw, direction) -> str` / `grid_area_identity(area) -> str` | Tariff-database ID of a catalog entry, `<LAND>/<direction>/<id>` or `<LAND>/grid/<id>` ([tariff-format.md](tariff-format.md) section 11); a `user_` entry is `DB_ID_UNAVAILABLE`, no `land` is `FIELD_MISSING`. |
| `tariff_version(raw, direction) -> str` / `grid_area_version(area, rule_sets) -> str` | Version hash (SHA-256, hex) over the price-relevant values; equal for equal prices however they are written. |
| `differs_from_db(raw, direction) -> bool \| None` | `None` without `db_ref`, else True when the prices no longer match `db_ref.version`. |
| `version_at(tariff, day) -> Tariff` | The validity version of `tariff` valid on `day` (house date); none is `TARIFF_NOT_VALID`. `evaluate` and the series call it per slot. |
| `read_package(path)` / `verify_package(document, *, trusted_keys=None, today=None) -> CatalogPackage` | Read and check a signed catalog package offline (section 11); `CatalogPackage.warnings` may hold `PACKAGE_EXPIRED`. |
| `plan_package_import(package, local_tariffs, local_grid_fees) -> ImportPlan` | `ImportPlan.changes` (`EntryChange`: `key`, `change` = `added` / `changed` / `removed`) and `ImportPlan.conflicts` (`MonthConflict`: `key`, `local_cent`, `package_cent`). |
| `apply_package_import(plan, resolutions) -> (tariffs, grid_fees)` | The new catalog documents; `resolutions` maps every conflict key to `KEEP_LOCAL` or `TAKE_PACKAGE`. |
| `write_catalog_pair(tariffs_path, tariffs, grid_path, grid_fees) -> None` | Writes both catalog files; both are complete on disk before either is replaced. |
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

## Price points

`PricePoint` (additive in `0.1.g`; both fields have defaults, so existing constructions keep working):

* `market_cent: float | None`: the market price the tariff used, cent/kWh, after hourly settlement for `settlement_mtu: 60min` spot tariffs and averaged over the point at 30/60 minutes; `None` for a tariff that uses no market price (also no rule on it).
* `method: str | None`: `exact` (`METHOD_EXACT`) for every point that is not a forecast; for a forecast point (`quality` `forecast`, at or after `forecast_from`) the `forecast_method` the caller passed, e.g. `mirror` (`METHOD_MIRROR`), `hold` (`METHOD_HOLD`) or a plug-in name. Without `forecast_method` it is `None`: Edibert does not invent a name. A 30/60-minute point with one forecast slot is a forecast point.
* `to_dict()` includes both.

## Market prices for ranges

`MarketArchive(zone, cache_dir, *, get=None, timeout=60, sleep=time.sleep, clock=None, retry_minutes=10, max_attempts=6)` with `.prices(start, end) -> MarketRange` returns day-ahead prices for `[start, end)` from Energy-Charts (free; AT, DE-LU, CH), no pandas.

* `start` / `end` must be aware and on 15-minute steps (`VALUE_INVALID` otherwise; a naive time has no instant without a house time zone). An unknown zone is `VALUE_INVALID`.
* Keys are UTC slot starts everywhere, so DST needs no special case: the autumn night has 100 slots and both 02:00 hours keep their own prices (Earnie's pandas loader groups naive local times and loses one of them). Hourly source data (before 2025-10-01) counts for its four quarter-hours; a gap in the source is never filled.
* Cache: one file per UTC calendar month, `<cache_dir>/market_archive/<zone>/YYYY-MM.json` (atomic writes). A month is asked again only while it is incomplete and could still change (not before `retry_minutes` since the last request); a month asked after its prices were final keeps its gaps. Months that start more than two days in the future are not requested. A damaged file is `MARKET_CACHE_UNREADABLE` and rebuilt.
* HTTP 429: waits for `Retry-After` (seconds) or `60 s x attempt`, up to `max_attempts` requests per month; then, like any source failure, `MARKET_SOURCE_FAILED`. `get`, `sleep` and `clock` are injectable for tests.
* `MarketRange`: `zone`, `start`, `end` (UTC), `prices` (`{slot_start_utc: cent/kWh}`, only slots with a price), `missing` (slots without one), `notes` (warnings), property `complete`. Missing slots are reported as `MARKET_RANGE_INCOMPLETE` (`zone`, `missing_from`, `missing_slots`); no price at all in the range is `MARKET_DATA_UNAVAILABLE`. `prices` goes straight into `tariff_price_series(market=...)`, which fails with `PRICE_MISSING` on a missing slot.

## Live market prices

`market_live(zone, data_dir, tz, ...)` returns `MarketData` for live operation (new in `0.1.k`; the publisher uses the same chain).

* Chain: cache `<data_dir>/market_<zone>.json` -> ENTSO-E (only with `entsoe_token`) -> Energy-Charts -> aWATTar (AT and DE-LU only; CH has no third source and no substitute). The sources are asked in order until one covers the whole window.
* Window: local midnight `history_days` days before today up to the end of today, or of tomorrow from 12:00 local time on (`tz`). `history_days` is `0` to `7` (the cache keeps 7 days), otherwise `VALUE_INVALID`; the lead days are fetched like today, so a fresh install has them too (for example mirror sources of a forecaster). An unknown zone is `VALUE_INVALID`.
* A cache that covers the window is used without a request. Otherwise the sources are asked, but not again within 10 minutes of the last request.
* `get` replaces the HTTP call for every source (`get(url, params, timeout) -> str`), e.g. a caller's own transport with recording or replay; default is plain `urllib`. A failing request (HTTP error, timeout, no connection) must raise `MarketSourceError`: the chain notes it as `MARKET_SOURCE_FAILED` and asks the next source. Any other exception ends the call (new in `0.1.6`).
* `MarketData`: `zone`, `prices` (`{slot_start_utc: cent/kWh}`, including the cached history), `source` (`entsoe`, `energy-charts`, `awattar`), `fetched_at`, `complete`, `notes`. A source that fails is `MARKET_SOURCE_FAILED` in `notes`; a partial answer is `complete == False` with `MARKET_DATA_INCOMPLETE` (`zone`, `missing_from`); no price at all and no cache is `MARKET_DATA_UNAVAILABLE`.

## Forecasters

The library takes a forecaster **object** implementing `Forecaster.forecast(known, start, end) -> {slot_start_utc: cent/kWh}`. A caller hands in its own model directly (Earnie: OLS model), no key involved. Plug-ins loaded from the entry-point group `edibert.forecasters` and their key (`EDIBERT_FORECAST_KEY`) belong to the product layer (`edibert.publish.forecasters`), not to the library.

## Editor embed (`edibert.ui.embed`)

The Streamlit editor as a component of a host page (new in `0.1.m`; Earnie's *Tarife* page). Not part of `edibert.api` and not counted in `API_VERSION`; needs the `ui` extra (`streamlit`).

* `render_editor(config, *, list_container=None, open_tariff=None)`: tariff list with new / copy / import, the four-step form and the preview with save. No `st.set_page_config`, no title, no language selector: the host owns the page and passes the language in `config`.
* `UiConfig(data_dir, catalog, language, key_prefix, host_house, delete_guard, on_change)`: the editor writes `<data_dir>/user_tariffs.json` (atomic, with `tariff_format`); `catalog` is the copy-as-template source (optional). `key_prefix` must be non-empty (`ValueError` otherwise); every session and widget key of the editor starts with it, so two embeds on one page keep separate state. `language` is `de` or `en` (`ValueError` otherwise) and is applied on every run.
* `HostHouse(context, grid_fee, capabilities, description)`: house facts of the host (`PricingContext`, resolved `GridFee` or `None`, `REQUIRES` capabilities). With a host house, the editor shows these values read-only and reads or writes no `house.json`; without one, it keeps its own house settings as the standalone page does.
* `delete_guard(direction, tariff_id) -> str | None` (optional, new in `0.1.o`): called when the user deletes a user tariff. A text is shown as a warning with *Delete anyway* / *Keep the tariff*, and the tariff is deleted only after the confirmation; `None` deletes right away (also the behaviour without a guard). Opening another tariff drops a pending confirmation.
* `on_change(action, direction, tariff_id)` (optional, new in `0.1.o`): called after the editor wrote `user_tariffs.json`: `"save"` after a save or for each imported tariff, `"delete"` after a delete; before the page reruns. Exceptions are not caught.
* `list_container`: Streamlit container for the house expander and the tool row (my tariffs with new / delete, copy from catalog, import; default since `0.1.p`: a container above form and preview, before: a column left of the form).
* Unsaved changes (new in `0.1.p`): while the open draft differs from its saved or freshly opened state, or is an unsaved catalog copy, the body shows *Nicht gespeichert* / *Not saved*, and opening another tariff, *new* or *copy* first shows a prompt with save (only for a valid draft; reports `on_change("save", …)`), discard and cancel (keys `leave.save`, `leave.discard`, `leave.cancel`). Delete and import do not leave the open draft and are not held; an `open_tariff` request of the host is not held either.
* `open_tariff=(direction, tariff_id)`: opens that user tariff once per distinct request; later reruns with the same request keep the user's edits. An unknown ID is shown as `TARIFF_NOT_FOUND` (`tariff_id`); an unknown direction is `ValueError`.
* New tariffs start with `land` = the land of the host house (`host_house.context.land`), or of the editor's own house settings; the field is visible in step 1 and may be cleared (then `land` is not written).
* `render_preview(tariff, house, *, language, key_prefix)`: hints and price curves of one parsed `Tariff` for a host house, for the host's preview of a selected tariff.
* After a save the page reruns and shows the success notice once. The standalone page (`python -m edibert ui`) runs the same code with the empty prefix.

## Types and constants

`TariffSet`, `Tariff`, `PriceResult`, `PricePoint`, `PriceSeries`, `PricingContext`, `GridArea`, `GridFee`, `GridFeeCatalog`, `GridFeeConfig`, `CapacityBand`, `CapacityCharge`, `CapacityState`, `CapacityLadder`, `LadderRung`, `HoldLastForecaster`, `MirrorForecaster`, `MarketArchive`, `MarketData`, `MarketRange`, `MarketSourceError`, `MigrationPlan`, `MigrationQuestion`, `MigrationBlocker`, `MigrationResult`, `DbRef`, `CatalogPackage`, `PackageManifest`, `ImportPlan`, `EntryChange`, `MonthConflict`; `KEEP_LOCAL`, `TAKE_PACKAGE`, `IMPORT`, `EXPORT`, `RESOLUTIONS`, `USER_PREFIX`, `TARIFF_FORMAT` (current version, `1`), `TARIFF_TRACK_FILES`, `STANDARD_VAT_PERCENT` (`{"AT": 20.0, "DE": 19.0, "CH": 8.1}`, prefill only), `METHOD_EXACT`, `METHOD_MIRROR`, `METHOD_HOLD`, `FALLBACK_PRIOR_YEAR` (`prior_year`), `FALLBACK_PRIOR_MONTH` (`prior_month`).

## Errors and warnings

`EdibertError` (`code: ErrorCode`, `params`) and `EdibertWarning` (`code: WarningCode`, `params`). Callers branch on the code, never on the English message.

New in `0.1.d`: tariffs take `valid_from` / `valid_to` (validity versions, `Tariff.periods`) and `db_ref` (`Tariff.db_ref`); errors `TARIFF_NOT_VALID` (`tariff_id`, `date`), `TARIFF_VALIDITY_OVERLAP` (`tariff_id`), `DB_ID_UNAVAILABLE` (`tariff_id`), `PACKAGE_FORMAT_UNSUPPORTED` (`value`), `PACKAGE_KEY_UNKNOWN` (`key_id`), `PACKAGE_SIGNATURE_INVALID` (`key_id`), `PACKAGE_CONTENT_MISMATCH` (`file`), `PACKAGE_IMPORT_CONFLICT` (`conflict`); warning `PACKAGE_EXPIRED` (`valid_until`). New dependency: `cryptography` (Ed25519).

New in `0.1.q`: errors `CAPACITY_CHARGE_MISSING` (`area_id`, `month`), `CAPACITY_STATE_MISSING` (`month`), `CAPACITY_STATE_MONTH_MISMATCH` (`month`, `state_month`); warnings `GRID_CAPACITY_SKIPPED_STATUS` (`charge_id`, `status`), `CAPACITY_BANDS_NOT_CONVEX` (`charge_id`), `CAPACITY_STATE_UNAVAILABLE` (`area_id`). Months are `YYYY-MM`.

New in `0.1.g` (warnings): `MONTH_RATE_FALLBACK` (`tariff_id`, `direction`, `month` and `used_month` as `YYYY-MM`, `rule` = `prior_year` / `prior_month`) and `MARKET_RANGE_INCOMPLETE` (`zone`, `missing_from`, `missing_slots`).
