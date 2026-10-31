# Library API (`edibert.api`)

Technical description of the public library facade for Earnie and other callers. Architecture: [architecture.md](architecture.md).

```python
from edibert import api
```

Only the names in `api.__all__` are covered by `api.API_VERSION` (currently `3`; raised from `1` to `2` by `0.1.i`: required `tariff_format`, required `netznutzung.area_id`, `GridFeeConfig` / `GridFee` without own values, `resolve_grid_fee` needs the area view, every tariff needs `vat_percent`; raised to `3` by `0.1.d` D1: `DbRef(id, version)` without `database`, `db_ref_for(raw, direction)`, package format 2; `0.1.d2` ships in the same release and stays `3`: a tariff with `grid_monthly_fee_eur` is `GRID_MONTHLY_FEE_LEGACY`, `grid_area_version` hashes the parsed area with its levy set, package grid areas need `check`). A breaking change to one of them raises the version; additions do not. Everything else in the package may change without notice. The API imports neither `edibert.ui` nor `edibert.publish` (checked by `tests/test_api.py`).

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
| `tariff_version(raw, direction) -> str` / `grid_area_version(area, rule_sets, levy_sets=None) -> str` | Version hash (SHA-256, hex) over the price-relevant values; equal for equal prices however they are written. A grid area that names a `levy_set` needs `levy_sets`. |
| `area_document(document, area_id) -> dict` / `grid_db_ref_for(document, area_id) -> dict` / `grid_differs_from_db(document, area_id) -> bool \| None` | `0.1.d2`: one area of a grid document with its rules and levies inlined (`{area, rules, levies}`), the `db_ref` a copy of a catalog area carries, and whether a user area with `db_ref` changed its prices. |
| `differs_from_db(raw, direction) -> bool \| None` | `None` without `db_ref`, else True when the prices no longer match `db_ref.version`. |
| `version_at(tariff, day) -> Tariff` | The validity version of `tariff` valid on `day` (house date); none is `TARIFF_NOT_VALID`. `evaluate` and the series call it per slot. |
| `read_package(path)` / `verify_package(document, *, trusted_keys=None, today=None) -> CatalogPackage` | Read and check a signed catalog package offline (section 11); `CatalogPackage.warnings` may hold `PACKAGE_EXPIRED`. |
| `plan_package_import(package, local_tariffs, local_grid_fees) -> ImportPlan` | `ImportPlan.changes` (`EntryChange`: `key`, `change` = `added` / `changed` / `removed`) and `ImportPlan.conflicts` (`MonthConflict`: `key`, `local_cent`, `package_cent`). |
| `apply_package_import(plan, resolutions) -> (tariffs, grid_fees)` | The new catalog documents; `resolutions` maps every conflict key to `KEEP_LOCAL` or `TAKE_PACKAGE`. |
| `write_catalog_pair(tariffs_path, tariffs, grid_path, grid_fees) -> None` | Writes both catalog files; both are complete on disk before either is replaced. |
| `plan_migration(docs, *, user_grid_areas=(), user_grid_rule_sets=None, grid_fee_area=None) -> MigrationPlan` | What `migrate` would change; see below. |
| `migrate(docs, answers=None, *, user_grid_areas=(), user_grid_rule_sets=None, grid_fee_area=None) -> MigrationResult` | Brings the tariff-track files to the current `tariff_format`; see below. |

## Migration of the tariff-track files

Pure functions: the caller reads the files, passes them as `docs = {file name: document}` (names from `TARIFF_TRACK_FILES`; a missing file is left out or `None`, any other name is `VALUE_INVALID`), and writes the returned documents itself with its own backup. What the step does is described in [tariff-format.md](tariff-format.md) section 2a.

* `user_grid_areas`: area objects (shape of an entry in `areas`, IDs `user_…`) to create in `user_grid_fees.json`; build an own flat price with `flat_user_grid_area`. Earnie passes one per house profile it moves off `area_id: null`. `user_grid_rule_sets`: rule sets (IDs `user_…`) the handed-in areas name (the stand-alone editor's own grid rules).
* `grid_fee_area`: the user area a `grid_monthly_fee_eur` of the user tariffs moves to (the area the house uses). `None`, a catalog area or an area that is not in `user_grid_fees.json` blocks such a move (`GRID_MONTHLY_FEE_NO_TARGET`), different values block it too (`GRID_MONTHLY_FEE_AMBIGUOUS`); see [tariff-format.md](tariff-format.md) section 2a, step 4. Earnie's pin bump decides the target per house profile.
* `MigrationPlan`: `current` (`tariff_format` per given file, `None` = untagged), `to_format`, `changed_files` (what `migrate` writes, assuming the questions get answered), `questions`, `blockers`, and the properties `needed` (anything to do) and `can_run` (no blockers).
* `MigrationQuestion`: `id` (key of the answer, e.g. `vat_percent:import:user_x`), `code` (`VAT_PERCENT`, UI text `question.VAT_PERCENT`), `file`, `kind` (`number`), `required` (`True`), `default` (prefill from `STANDARD_VAT_PERCENT` by the tariff's `land`, or `None`), `params` (`tariff_id`, `label`, `direction`, `prices` = `gross` / `net`, `land`). Asked for every user tariff without a rate, gross or net.
* `MigrationBlocker`: `code` (an `ErrorCode`, UI text `error.<code>`), `file`, `params`, `message` (English, for logs). Blockers: `FORMAT_UNSUPPORTED`, `GRID_ID_COLLISION` (a user area or rule set exists with other values), `GRID_MONTHLY_FEE_AMBIGUOUS`, `GRID_MONTHLY_FEE_NO_TARGET`, and the first load error per file of the migrated documents (e.g. `VAT_PERCENT_MISSING` in the catalog, `GRID_ID_PREFIX_MISSING` for a handed-in area).
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

* `render_editor(config, *, share_default, list_container=None, open_tariff=None)`: tariff list with new / copy / import, the share section, the four-step form and the preview with save. No `st.set_page_config`, no title, no language selector: the host owns the page and passes the language in `config`.
* `share_default` (required, new in `0.1.d` Catalog P6): `ShareDefault.OPT_IN` (Earnie: nothing is selected until the user ticks it) or `ShareDefault.SHARE` (stand-alone Edibert: every shareable tariff starts selected). There is no default; a missing value is a `TypeError`, any other value too.
* `UiConfig(..., contribution_transport=None)` (new in `0.1.d` Catalog P6): the adapter that sends shared tariffs, see *Sharing with the tariff database*. `None` means no endpoint is configured: the share section says so (`CONTRIBUTION_TRANSPORT_OFF`) and its send button stays disabled. The share section uses the keys `share.<direction>.<tariff_id>` (checkbox) and `share.send`.
* `UiConfig(..., exchange=None)` (new in `0.1.d` S3): the `ExchangeClient` of the tariff database server. The stand-alone page builds it from the environment (`None` with `EDIBERT_EXCHANGE_OFF=1`); a host passes its own or leaves it `None`. With a client the form of a tariff whose prices still match its `db_ref` shows the database status (trust level, check date and "check overdue", installations in 12 months, newer or checked version, merge hint with the confirmed re-link `db_status.relink_ask|yes|no.<db_id>`) and the button `db_status.ask.<db_id>`; without one it shows the status the publisher saved in `exchange_state.json` (state format 2), if any. With a client the tools row also shows the template list behind the opt-in `templates.opt_in` (`templates.land`, `templates.direction`, `templates.supplier`, `templates.load`, `templates.copy`). The package import of the stand-alone sidebar gets the button `package.fetch` (the catalog package, no key).
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

## Sharing with the tariff database (`edibert.contribution`)

New in `0.1.d` Catalog P6. Not part of `edibert.api` yet and not counted in `API_VERSION` until the server runs. Nothing in Edibert sends anything without a transport the caller passes in; the server transport is `edibert.exchange.ServerTransport` (below).

| Name | Purpose |
|---|---|
| `contribution_payload(raw, direction) -> dict` | The payload of one user tariff (the object stored in `user_tariffs.json`): `{"contribution_format": 1, "direction", "tariff"}`. The tariff is checked with `parse_tariff` first (an invalid tariff is never shared, its own error code is raised), then copied field by field from `TARIFF_WHITELIST` (type, `label` as product name, `supplier_id`, `land`, `regions`, `currency`, all price, fee and VAT fields, `rules`, floor / cap, `requires`, `holidays`, `extra_holiday_dates`, `source`, `last_verified`; reserved for later formats: `area_id`, `valid_from`, `valid_to`). Rules keep `RULE_WHITELIST` (no `label`); nested objects keep their known keys. Dropped: `id`, `notes`, `behavior_notes`, `$comment` at every level, `individual`, `applies_to`, `monthly_seed`. `individual: true` is `CONTRIBUTION_INDIVIDUAL` (`tariff_id`); a tariff without `land` is `CONTRIBUTION_LAND_MISSING` (`tariff_id`), because the server files it under its land. The server transport adds `version` (and `based_on`) when it sends, see [catalog-exchange.md](catalog-exchange.md). |
| `payload_text(payload) -> str` | The exact text of a payload (sorted keys, indent 2, UTF-8): shown in the preview and sent by a transport unchanged. |
| `contribution_items(document) -> list[ContributionItem]` | Every tariff of a user document, imports first: `direction`, `tariff_id`, `label`, and either `payload` or the coded `error` that keeps it from being shared; `db_ref` of the tariff (or `None`). |
| `ShareDefault` | `SHARE` / `OPT_IN`; `check_share_default(value)` raises `TypeError` for anything else. |
| `initially_selected(item, share_default) -> bool` | Start value of the per-tariff choice; always `False` for an item with an error. |
| `ContributionTransport` | Protocol: `send(payload, db_ref) -> SendResult`; `db_ref` is the item's database entry (sent as `based_on`) or `None`. An implementation sends `payload_text(payload)` unchanged and raises a coded `EdibertError` when it cannot deliver. |
| `SendResult(status, code=None, db_ref=None)`, `SendStatus` | `accepted` / `duplicate` / `rejected` with an optional reason code; `db_ref` is the database entry an accepted or duplicate tariff now stands for. The share section writes it into the user tariff. |
| `send_selected(transport, items) -> list[SendResult]` | One `send` per `ContributionItem` (payload and `db_ref`), in order; `transport=None` is `CONTRIBUTION_TRANSPORT_OFF`, an item that cannot be shared is a `ValueError`. |

## Exchange with the tariff database server (`edibert.exchange`)

New in `0.1.d` Catalog P7, contract v2 since `0.1.d` D3; contract [catalog-exchange.md](catalog-exchange.md). Not part of `edibert.api` yet. Every request raises `EXCHANGE_OFF` while `EDIBERT_EXCHANGE_OFF=1`, whatever the caller configured; no request carries an installation ID.

| Name | Purpose |
|---|---|
| `ExchangeConfig(base_url, timeout_s=20)` | Server of the tariff database (free, no key). `exchange_config_from_env()`: `None` when switched off, else `EDIBERT_EXCHANGE_URL` (default `DEFAULT_BASE_URL`). |
| `ExchangeClient(config, send=urllib_send)` | `fetch_package(known_package_id=None)` (route 1, the catalog package; `None` when unchanged; the caller verifies and imports), `submit(payload, db_ref=None) -> SubmitAnswer` (route 2), `report_usage(db_id, version, pseudonym)` (route 3), `query_status([(db_id, version)]) -> list[StatusEntry]` (route 4, chunks of 100; `check_state`, `checked_at`, `latest_checked_version`, `merged_into`, properties `outdated`, `checked_available`), `list_templates(land, direction, grid_area=None, supplier=None) -> TemplateList` (route 5; filters checked before asking, `VALUE_INVALID`; each `Template` with its recomputed version, `db_ref`). `send(method, url, body, headers, timeout) -> HttpAnswer` is injectable. |
| `ServerTransport(client)` | The `ContributionTransport` of the share section. `ui.config.config_from_env()` (stand-alone editor) sets it unless switched off; a host passes its own or `None`. |
| `install_secret(data_dir) -> bytes`, `usage_pseudonym(secret, db_id) -> str` | The installation's secret in `exchange_secret` (created on first use, never sent) and the per-tariff pseudonym `HMAC-SHA256(secret, db_id)`. |
| `used_ref(raw, direction, from_package)` | The `DbRef` a tariff in use stands for, or `None`: a user tariff's unchanged `db_ref`, or a catalog tariff of a package catalog (`from_package`). |
| `plan_usage_reports(refs, secret, start, rng=None) -> list[UsageReport]` | One report per distinct entry at a random time within 24 h, sorted by time; the caller sends each one alone. |
| `payload_version(payload) -> str` | `tariff_version` of a share payload. |
| `edibert.ui.templates.template_copy(template, taken, label_suffix)` | The user tariff a template becomes: new `user_` ID, the template's `db_ref`. |

Errors: `EXCHANGE_OFF` (`env`), `EXCHANGE_UNREACHABLE` (`route`), `EXCHANGE_ACCESS_DENIED` / `EXCHANGE_REJECTED` (`route`, `server_code`), `EXCHANGE_RATE_LIMITED` (`route`, `retry_after`), `EXCHANGE_ANSWER_INVALID` (`route`).

## Types and constants

`TariffSet`, `Tariff`, `PriceResult`, `PricePoint`, `PriceSeries`, `PricingContext`, `GridArea`, `GridFee`, `GridFeeCatalog`, `GridFeeConfig`, `CapacityBand`, `CapacityCharge`, `CapacityState`, `CapacityLadder`, `LadderRung`, `HoldLastForecaster`, `MirrorForecaster`, `MarketArchive`, `MarketData`, `MarketRange`, `MarketSourceError`, `MigrationPlan`, `MigrationQuestion`, `MigrationBlocker`, `MigrationResult`, `DbRef` (`id`, `version`), `CatalogCheck` (`state`, `checked_at`, `source`, `released_by`), `CatalogPackage`, `PackageManifest`, `ImportPlan`, `EntryChange`, `MonthConflict`; `KEEP_LOCAL`, `TAKE_PACKAGE`, `IMPORT`, `EXPORT`, `RESOLUTIONS`, `USER_PREFIX`, `TARIFF_FORMAT` (current version, `1`), `TARIFF_TRACK_FILES`, `STANDARD_VAT_PERCENT` (`{"AT": 20.0, "DE": 19.0, "CH": 8.1}`, prefill only), `METHOD_EXACT`, `METHOD_MIRROR`, `METHOD_HOLD`, `FALLBACK_PRIOR_YEAR` (`prior_year`), `FALLBACK_PRIOR_MONTH` (`prior_month`), `CHECK_STATES` (`unchecked`, `checked`, `released_by_supplier`, `rejected`), `TRUST_LEVELS` (strongest first).

Trust (`0.1.d` D4): `trust_level(check_state, reliable) -> str` (released by supplier > checked > reliable > unchecked; derived, never stored), `check_overdue(check_state, checked_at, today, *, grid_fee=False) -> bool` (a checked or supplier-released version older than 91 days plus 30; a grid fee also once 1 January passed and the check is from an earlier year).

## Errors and warnings

`EdibertError` (`code: ErrorCode`, `params`) and `EdibertWarning` (`code: WarningCode`, `params`). Callers branch on the code, never on the English message.

New in `0.1.d`: tariffs take `valid_from` / `valid_to` (validity versions, `Tariff.periods`) and `db_ref` (`Tariff.db_ref`); errors `TARIFF_NOT_VALID` (`tariff_id`, `date`), `TARIFF_VALIDITY_OVERLAP` (`tariff_id`), `DB_ID_UNAVAILABLE` (`tariff_id`), `PACKAGE_FORMAT_UNSUPPORTED` (`value`), `PACKAGE_KEY_UNKNOWN` (`key_id`), `PACKAGE_SIGNATURE_INVALID` (`key_id`), `PACKAGE_CONTENT_MISMATCH` (`file`), `PACKAGE_IMPORT_CONFLICT` (`conflict`); warning `PACKAGE_EXPIRED` (`valid_until`). New dependency: `cryptography` (Ed25519). Contract v2 (`0.1.d` D1, D2): `Tariff.check` (`CatalogCheck`, catalog entries of a package), errors `DB_REF_LEGACY` (`path`; a `db_ref` with `database`, removed by `migrate`), `CHECK_NOT_IN_USER_FILE` (`tariff_id`), `PACKAGE_ENTRY_UNCHECKED` (`tariff_id`).

New in `0.1.d` Catalog P6: errors `CONTRIBUTION_INDIVIDUAL` (`tariff_id`), `CONTRIBUTION_LAND_MISSING` (`tariff_id`), `CONTRIBUTION_TRANSPORT_OFF`; warning `CONTRIBUTION_TRANSPORT_OFF` (shown by the share section while no transport is configured).

New in `0.1.q`: errors `CAPACITY_CHARGE_MISSING` (`area_id`, `month`), `CAPACITY_STATE_MISSING` (`month`), `CAPACITY_STATE_MONTH_MISMATCH` (`month`, `state_month`); warnings `GRID_CAPACITY_SKIPPED_STATUS` (`charge_id`, `status`), `CAPACITY_BANDS_NOT_CONVEX` (`charge_id`), `CAPACITY_STATE_UNAVAILABLE` (`area_id`). Months are `YYYY-MM`.

New in `0.1.g` (warnings): `MONTH_RATE_FALLBACK` (`tariff_id`, `direction`, `month` and `used_month` as `YYYY-MM`, `rule` = `prior_year` / `prior_month`) and `MARKET_RANGE_INCOMPLETE` (`zone`, `missing_from`, `missing_slots`).
