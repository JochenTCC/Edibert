# Completed Items

Archive of completed work. Open todos → [Backlog.md](Backlog.md) · Bugfixes → [Backlog-Bugfixes.md](Backlog-Bugfixes.md).

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
