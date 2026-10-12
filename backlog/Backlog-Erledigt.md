# Completed Items

Archive of completed work. Open todos → [Backlog.md](Backlog.md) · Bugfixes → [Backlog-Bugfixes.md](Backlog-Bugfixes.md).

### Engine P2 — grid fee and price series (0.1.b, 2026-10-12)

- [x] **0.1.b — Engine P2** (`src/edbert/`: `gridfee.py`, `series.py`, `checks.py`; extensions in `rules.py`, `tariff.py`, `cli.py`)
  - Grid fee (`netznutzung`) in Earnie's shape: catalog areas (`grid_fees.json`), metering type, `quarter_hour_meter`, rule status and `include_status`, own rules without a catalog area (section 14a module 3 levels), holiday handling; included rule without a value is an error
  - Grid fee added in `evaluate` before VAT (import only); `PriceResult` carries grid fee and rule
  - `tariff_price_series`: horizon, resolution 15/30/60 min, UTC slot stepping (DST days 92/100 slots), market prices per slot with strict missing-price errors, hour-mean for hourly settled spot tariffs, components (supplier, grid, VAT), quality `exact`/`forecast`, JSON output
  - Warnings (coded, translated): hour-misaligned windows in hourly tariffs, unmet requirements, skipped grid rules
  - Command line: `price` with `--grid-fee`/`--grid-catalog`, new `series` (market CSV, table or JSON), `--has` for house capabilities
  - Verified against Earnie `main` (`data/grid_fees.py`, `tariff_pricing.py`): 45,136 grid-fee comparisons over 14 areas and 180 configurations and 6,300 tariff-plus-grid-fee comparisons without a difference; both raise in the same 56 configurations (included rule without value)
  - 126 tests, 96 % line coverage, ruff and vulture clean
  - Open for the quality gate `0.1.r`: `rules.py` (365 lines) and `tariff.py` (303) are above the 300-line target (below the hard limit); `schema._tariff_properties` is 53 lines; JSON Schema for the `netznutzung` field is not generated yet

### Engine P1 — rule engine, user tariffs, holidays (0.1.a, 2026-10-12)

- [x] **0.1.a — Engine P1** (`src/edbert/`: `rules.py`, `tariff.py`, `context.py`, `store.py`, `schema.py`, `cli.py`)
  - Strict tariff parser (unknown fields, `tiers`/`demand` and `applies_to` other than `"main"` rejected with coded errors); time rules with months, weekdays (numbers, names, groups, `holiday`), windows over midnight, validity, effects `absolute_cent` / `add_cent` / `percent_off`, market-price filter `when_market_cent_kwh`; first match wins; price floor/cap; VAT; evaluation per 15-minute slot in the house time zone
  - Holidays via `holidays` (MIT, offline): `treat_as` sunday | weekday | own, `extra_holiday_dates`, region required only when holidays can change a result
  - Loader for `tariffs.json` plus `user_tariffs.json` (ID collision, `user_` prefix rules, optional user file, broken files as coded errors)
  - Command line `python -m edbert price …` and `python -m edbert schema`; generated `schema/tariff.schema.json` with a consistency test
  - Verified against the Earnie catalog (35 import and 13 export tariffs load); 2466 price comparisons against Earnie's `data/tariff_pricing.py` without a difference (months missing in a `monthly_table` are strict errors here by design)
  - 83 tests, 96 % line coverage, ruff and vulture clean; no function over 40 lines, no file over 300 lines
  - Not part of 0.1.a any more: Westnetz §14a fixture and grid-fee step (moved to 0.1.b)

### Language policy and multilingual foundation (2026-10-12)

- [x] **Language policy** — technical documents English only; README and user manuals in English (authoritative) and German (`README.de.md`, `docs/user/en|de/`); legal texts per country in the national language (DE/AT/CH: German); rule `docs-language.mdc` replaces `german-user-docs.mdc`
- [x] **Multilingual skeleton** — `edbert.i18n` (`Translator`, `en`/`de` catalogs), `edbert.errors` (`EdbertError`, `ErrorCode`), catalog parity tests, docs translation test, user manual placeholders

### Repository scaffold (2026-10-12)

- [x] **Repository scaffold** — local repo with README, `LICENSE` (PolyForm Noncommercial 1.0.0, verbatim) and `NOTICE`, contributing guide, format spec draft (`docs/spec/tariff-format.md`), four example tariffs, smoke tests, package skeleton `src/edbert/`
- [x] **Rules and skills ported from Earnie** — `.cursor/rules` (no-implicit-fallbacks, powershell-shell, german-user-docs (later replaced by docs-language), english-chat, versioning, backlog, roadmap-nomenclature, backlog-anonymize-users, edbert-project) and `.cursor/skills` (windows-unicode-console, bugfix-regression-test, doc-review-findings, session-abschluss, quality-gate)
- [x] **Draft legal texts moved out of the repo** — catalog terms, contribution terms, privacy notice and review checklist live in the Earnie project folder until legally reviewed
