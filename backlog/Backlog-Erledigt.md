# Completed Items

Archive of completed work. Open todos → [Backlog.md](Backlog.md) · Bugfixes → [Backlog-Bugfixes.md](Backlog-Bugfixes.md).

### Tariff supply for the past and the future (0.1.g, 2026-10-26)

- [x] **0.1.g — Tariff supply for the past and the future** (Earnie epic `Edibert` P3a-2; `src/edibert/tariff.py`, `src/edibert/series.py`, `src/edibert/market/archive.py`; spec `docs/spec/api.md`, `docs/spec/tariff-format.md` sections 3 and 8)
  - Monthly-table fallback in Earnie's order for import and export: exact month → same month of the previous year (`prior_year`) → previous calendar month (`prior_month`, January looks at December), no further step; otherwise `PRICE_MISSING` (also before a table starts); coded warning `MONTH_RATE_FALLBACK` (`tariff_id`, `direction`, `month`, `used_month`, `rule`) on `PriceResult.warnings` and once per month on `PriceSeries.warnings`, also when a 72-hour window crosses the month change; editor preview, price probe and invoice check show it
  - `PricePoint.market_cent` (after hourly settlement, mean over the point, `None` without market price) and `PricePoint.method` (`exact`, or the new `forecast_method` argument of `tariff_price_series`; `None` when the caller names none); publisher and CLI (`--forecast-method`) pass the method
  - Market prices for arbitrary ranges: `MarketArchive` / `api.market_range` (Energy-Charts, no pandas), UTC keys end to end (autumn DST night keeps both 02:00 hours), one cache file per UTC month, refetch only while a month can still change, HTTP 429 waited out (`Retry-After` or 60 s × attempt, `RateLimited`), gaps reported as `MARKET_RANGE_INCOMPLETE` and never filled (also a gap in the Energy-Charts timestamps, which the parser used to fill); `api.known_at` for prices known at a planning moment; `api.market_zone`
  - Compatibility with Earnie: Earnie's P3a fixture (9 tariffs × 4 windows) plus Earnie's values on the monthly-table edge months (export tables ending 2026-09, `monthly_sunny_web_recherche` 2026-10, `at_vkw_strom_duo` 2027-03, an error before a table starts and beyond one step back, a placeholder table for `prior_month` across the year boundary) in `tests/fixtures/earnie_parity/` with the generator `make_fixture.py`; triaged deviation T1 (autumn DST, hourly settled spot) asserted explicitly
  - Additive to `edibert.api`, `API_VERSION` stays 2; tests `tests/test_monthly_fallback.py`, `tests/test_market_archive.py`, `tests/test_earnie_parity.py`, cases in `tests/test_series.py` and `tests/test_ui_app.py`; full suite green (401 passed, 1 skipped; the skipped Streamlit file passes with Streamlit installed, 12 passed)
  - Left open: tariffs that change over time (new prices from a date), now an item under `0.+1`

### Library API parse_tariff (0.1.j, 2026-10-26)

- [x] **0.1.j — Library API: `parse_tariff`** (Earnie epic `Edibert` P3a, triage T3; `src/edibert/api.py`, spec `docs/spec/api.md`)
  - `api.parse_tariff(raw, direction)`: one tariff object checked exactly like a file entry (unknown and unsupported fields, type fields, mandatory `vat_percent`), without the `user_` prefix rule and without `tariff_format`; re-export of `edibert.tariff.parse_tariff`; additive, `API_VERSION` stays 2
  - Earnie builds its scenario shortcut *Eigener Festpreis* (`__user_fixed__`, no tariff file) with it
  - Test `tests/test_api.py`; full suite green (308 passed, 1 skipped); released as `0.1.3` with tag `v0.1.3` (approved 2026-10-26)

### Tariff-format version, user grid areas and migrations (0.1.i, 2026-10-26)

- [x] **0.1.i — Tariff-format version, user grid areas and migrations** (Part A of Earnie epic `Edibert` P2; `src/edibert/fileformat.py`, `src/edibert/migration.py`, `src/edibert/gridfee.py`; spec `docs/spec/tariff-format.md` sections 2, 2a, 5a, `docs/spec/api.md`)
  - Format version: root key `tariff_format` (current `1`) required in `tariffs.json`, `user_tariffs.json`, `grid_fees.json`, `user_grid_fees.json`; missing is `FORMAT_MISSING`, unknown is `FORMAT_UNSUPPORTED`; `earnie_data_model` left `ROOT_FIELDS` (only the migration reads it); the editor creates `user_tariffs.json` with the key and refuses to write into an unmigrated file; a pasted import document may omit the key but not state an unknown one
  - User grid areas: `user_grid_fees.json` with the shape of `grid_fees.json`, `user_` prefix for areas and rule sets (`GRID_ID_PREFIX_MISSING` / `GRID_ID_PREFIX_RESERVED`), `GRID_ID_COLLISION`; user rules may omit `status`; merged view with origin per area (`api.load_grid_fees`), writer `api.save_user_grid_area`, helper `api.flat_user_grid_area`; CLI option `--user-grid-fees`
  - Smaller `netznutzung`: `area_id` (required), `power_metering`, `quarter_hour_meter`, `include_status`; own values only in a user area; the editor's own grid fee resolves through an in-memory user area (`house.json` unchanged); example split into `grid_fee_modul3_example.json` (user grid file) and `netznutzung_modul3_example.json` (selection)
  - `vat_percent` required on every tariff, gross or net (`VAT_PERCENT_MISSING`, `0` allowed), also in the JSON schema; decided 2026-10-26, stricter than Earnie memo D3b (gross only), because net prices get the rate added
  - Migration API: `api.plan_migration` / `api.migrate` (pure, docs in and out): tagging, `earnie_data_model` removal, user grid areas from the caller, VAT question `VAT_PERCENT` for every user tariff without a rate, prefill AT 20 / DE 19 / CH 8.1 (written only from an answer), blockers with error codes, idempotent; `API_VERSION` 2
  - Tests: `tests/test_migration.py`, `tests/test_gridfee.py` rewritten, format and VAT cases in the store, user-store and schema tests; full suite green (303 passed, 1 skipped)
  - Same release: bugfix VAT on the net grid fee for gross tariffs (`Backlog-Bugfixes.md`, Verifications Pending); released as `0.1.2` with tag `v0.1.2` (approved 2026-10-26); Earnie P2 raises its pin and adapts its callers

### Library API and layering (0.1.f, 2026-10-26)

- [x] **0.1.f — Library API and layering** (`src/edibert/api.py`, spec `docs/spec/api.md`)
  - Public facade `edibert.api` with `API_VERSION = 1`: `load_tariffs` (catalog + optional user file, origin per tariff), `load_grid_fee_catalog`, `parse_grid_fee_config`, `resolve_grid_fee`, `pricing_context` (region checked up front: `HOLIDAY_REGION_UNKNOWN`; region without land: `FIELD_MISSING`), `tariff_price_series`, `evaluate`, `price_cent`, `builtin_forecaster`; types, constants, error and warning codes re-exported
  - Layering test: no library module imports `edibert.ui` or `edibert.publish` (static scan), and `import edibert.api` loads no product module (fresh interpreter)
  - Forecaster split: the library keeps the `Forecaster` interface and the free methods (`builtin_forecaster`, `mirror` / `hold`); plug-in loading with the key (`load_forecaster`, `available_forecasters`, `build_forecaster`, `EDIBERT_FORECAST_KEY`) moved to `edibert.publish.forecasters`
  - Check against Earnie: `share/config/tariffs.json` (50 tariffs) and `grid_fees.json` (14 areas) load through `edibert.api` without error
  - Open: `tariff_format` root key and migration functions (`plan_migration` / `migrate`) are a format decision for the Earnie integration (Earnie config-migration draft §3.7), not taken here

### MQTT publisher and market price chain (0.1.e, 2026-10-12)

- [x] **0.1.e — Publish P2: MQTT** (`src/edibert/market/`, `src/edibert/publish/`, command `python -m edibert publish`)
  - Market chain as in Earnie: cache -> ENTSO-E A44 (env `ENTSOE_API_TOKEN`) -> Energy-Charts -> aWATTar (AT/DE only); EUR/MWh to cent/kWh, hourly data expanded to quarter hours, A03 gaps carried forward, finer resolution wins; zone by country (AT, DE-LU, CH)
  - Freshness by slot coverage with publish hour 12 (tomorrow expected from then on), DST-safe windows (92/100 slots), 10-minute retry pause, best partial answer with a coded warning, strict error if nothing is available; cache file per zone (atomic), damaged cache is a warning
  - Publisher: retained topics `state` (EUR/kWh), `attributes` (`raw_today`, `raw_tomorrow`, `forecast`, components, day statistics, market block with attribution), `availability`, bridge status with last will; Home Assistant discovery; tariffs without data go offline instead of guessing; credentials only via named environment variables
  - Forecast: free methods `mirror` (same time of day, up to 7 days back, as in Earnie) and `hold` (last price constant); key-gated plug-in hook (entry-point group `edibert.forecasters`, key from `EDIBERT_FORECAST_KEY`, validated by the plug-in; none shipped in the free edition); forecast cut at the last gap-free whole hour; cache keeps 7 days of history; failing plug-ins never touch exact prices. Issuing and checking keys: open
  - New coded errors/warnings with en/de texts, CLI `publish` (`--once`, `--dry-run`), user manual page en/de, spec `docs/spec/publishing.md`
  - 253 tests (75 new, fake HTTP and fake MQTT), 95 % line coverage, ruff and vulture clean; smoke test against the live Energy-Charts API
  - Open for `0.1.r`: the default `http_get` is not covered by a test; no real broker test yet (needs a Mosquitto run); `cli.py` is above the file-size target

### Editor — form model, preview, import, Streamlit front end (0.1.c, 2026-10-12)

- [x] **0.1.c — Editor** (`src/edibert/editor/` without UI, `src/edibert/ui/` Streamlit)
  - Editor P1 (no UI): form model (`TariffDraft`/`RuleDraft`, round trip to tariff JSON, unknown fields kept, unique rule IDs, name required), rule templates (night, weekend, summer midday, high/low tariff), plausibility checks (rule hidden behind another, rule that never applies, unusual prices, gross spot prices), preview data (typical days, holiday day, DST-safe curves, example market curve), invoice check (bands per month, fees with VAT, 2 % tolerance), house settings (`house.json`), user store (atomic writes of `user_tariffs.json`)
  - Editor P2: Streamlit page with four steps, live price curve, price at a time, invoice check, hints, house settings with grid-fee rows, language selector (en/de, values kept on switch), `python -m edibert ui`
  - Editor P3: copy a catalog tariff as template (I1), import JSON from text or file with rename, collision and error report (I2)
  - Coded errors with readable field names; 30+ new catalog texts per language; user manual en/de (7 pages)
  - Rules and skills ported from Earnie: `streamlit-ui-state`, `streamlit-apptest`
  - 178 tests including 11 headless AppTest flows
  - Open for `0.1.r`: visual check of the page in a browser was only partial (the browser pane failed to draw screenshots); no screenshots in the manual yet; `st.data_editor` (monthly prices) is not covered by AppTest

### Engine P2 — grid fee and price series (0.1.b, 2026-10-12)

- [x] **0.1.b — Engine P2** (`src/edibert/`: `gridfee.py`, `series.py`, `checks.py`; extensions in `rules.py`, `tariff.py`, `cli.py`)
  - Grid fee (`netznutzung`) in Earnie's shape: catalog areas (`grid_fees.json`), metering type, `quarter_hour_meter`, rule status and `include_status`, own rules without a catalog area (section 14a module 3 levels), holiday handling; included rule without a value is an error
  - Grid fee added in `evaluate` before VAT (import only); `PriceResult` carries grid fee and rule
  - `tariff_price_series`: horizon, resolution 15/30/60 min, UTC slot stepping (DST days 92/100 slots), market prices per slot with strict missing-price errors, hour-mean for hourly settled spot tariffs, components (supplier, grid, VAT), quality `exact`/`forecast`, JSON output
  - Warnings (coded, translated): hour-misaligned windows in hourly tariffs, unmet requirements, skipped grid rules
  - Command line: `price` with `--grid-fee`/`--grid-catalog`, new `series` (market CSV, table or JSON), `--has` for house capabilities
  - Verified against Earnie `main` (`data/grid_fees.py`, `tariff_pricing.py`): 45,136 grid-fee comparisons over 14 areas and 180 configurations and 6,300 tariff-plus-grid-fee comparisons without a difference; both raise in the same 56 configurations (included rule without value)
  - 126 tests, 96 % line coverage, ruff and vulture clean
  - Open for the quality gate `0.1.r`: `rules.py` (365 lines) and `tariff.py` (303) are above the 300-line target (below the hard limit); `schema._tariff_properties` is 53 lines; JSON Schema for the `netznutzung` field is not generated yet

### Engine P1 — rule engine, user tariffs, holidays (0.1.a, 2026-10-12)

- [x] **0.1.a — Engine P1** (`src/edibert/`: `rules.py`, `tariff.py`, `context.py`, `store.py`, `schema.py`, `cli.py`)
  - Strict tariff parser (unknown fields, `tiers`/`demand` and `applies_to` other than `"main"` rejected with coded errors); time rules with months, weekdays (numbers, names, groups, `holiday`), windows over midnight, validity, effects `absolute_cent` / `add_cent` / `percent_off`, market-price filter `when_market_cent_kwh`; first match wins; price floor/cap; VAT; evaluation per 15-minute slot in the house time zone
  - Holidays via `holidays` (MIT, offline): `treat_as` sunday | weekday | own, `extra_holiday_dates`, region required only when holidays can change a result
  - Loader for `tariffs.json` plus `user_tariffs.json` (ID collision, `user_` prefix rules, optional user file, broken files as coded errors)
  - Command line `python -m edibert price …` and `python -m edibert schema`; generated `schema/tariff.schema.json` with a consistency test
  - Verified against the Earnie catalog (35 import and 13 export tariffs load); 2466 price comparisons against Earnie's `data/tariff_pricing.py` without a difference (months missing in a `monthly_table` are strict errors here by design)
  - 83 tests, 96 % line coverage, ruff and vulture clean; no function over 40 lines, no file over 300 lines
  - Not part of 0.1.a any more: Westnetz §14a fixture and grid-fee step (moved to 0.1.b)

### Language policy and multilingual foundation (2026-10-12)

- [x] **Language policy** — technical documents English only; README and user manuals in English (authoritative) and German (`README.de.md`, `docs/user/en|de/`); legal texts per country in the national language (DE/AT/CH: German); rule `docs-language.mdc` replaces `german-user-docs.mdc`
- [x] **Multilingual skeleton** — `edibert.i18n` (`Translator`, `en`/`de` catalogs), `edibert.errors` (`EdibertError`, `ErrorCode`), catalog parity tests, docs translation test, user manual placeholders

### Repository scaffold (2026-10-12)

- [x] **Repository scaffold** — local repo with README, `LICENSE` (PolyForm Noncommercial 1.0.0, verbatim) and `NOTICE`, contributing guide, format spec draft (`docs/spec/tariff-format.md`), four example tariffs, smoke tests, package skeleton `src/edibert/`
- [x] **Rules and skills ported from Earnie** — `.cursor/rules` (no-implicit-fallbacks, powershell-shell, german-user-docs (later replaced by docs-language), english-chat, versioning, backlog, roadmap-nomenclature, backlog-anonymize-users, edibert-project) and `.cursor/skills` (windows-unicode-console, bugfix-regression-test, doc-review-findings, session-abschluss, quality-gate)
- [x] **Draft legal texts moved out of the repo** — catalog terms, contribution terms, privacy notice and review checklist live in the Earnie project folder until legally reviewed
