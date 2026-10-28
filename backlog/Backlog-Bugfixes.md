# Open Bugs

Completed items → [Backlog-Erledigt.md](Backlog-Erledigt.md) (sections `### Bugfix …` / `### Document Review …`)

Feature roadmap → [Backlog.md](Backlog.md)

## Classification

Group open bugs by topic chapters (`## Bug <Topic>`). Each code bugfix gets a regression test proposal (skill `bugfix-regression-test`).

## Bugfix Verifications Pending

Fix is implemented and committed, acceptance (real tariff check, Home Assistant test, reporter confirmation) is outstanding. Do not archive before acceptance.

- [ ] **Gross tariff: net grid fee added without VAT** *(fixed in 0.1.i, 2026-10-26)* — `tariff.evaluate` added the net grid fee to a gross supplier price without VAT (30 ct + 8 ct = 38 ct instead of 39.6 ct at 20 %); Earnie puts the VAT on it (`grid_fee_on_tariff_basis`). Now: gross prices get `grid_fee * (1 + vat_percent/100)`, net prices `(supplier + grid fee) * (1 + vat_percent/100)`; `vat_cent` of a gross price point is the VAT on the grid fee. Affects editor preview, invoice check and the MQTT publisher. Regression test: `tests/test_grid_fee_vat_regression.py`. Acceptance: Earnie P3a comparison against Earnie's engine with a gross tariff and a grid fee
- [ ] **Editor hint on missing months is stale** *(found in Earnie P7 S1, 2026-10-27; fixed in 0.1.h S1, 2026-10-28)* — `ui.monthly_hint` (en, de) said a missing month stops the calculation; since `0.1.g` a missing month uses the prior-year / prior-month rate with the warning `MONTH_RATE_FALLBACK`. Now both catalogs say so, in the wording of the user manual (`docs/user/*/editor.md`). Regression test: `tests/test_ui_app.py::test_monthly_step_hint_describes_the_month_rate_fallback` (en, de). Acceptance: the monthly step in the editor (standalone and embedded in Earnie) shows the new text

## Bug Editor monthly-rate table (follow-ups of 0.1.h, 2026-10-28)

- [ ] **Earnie data with a month listed twice no longer loads** — since `0.1.h` S2 a duplicate `(year, month)` in `monthly_rates` is the error `MONTH_RATE_DUPLICATE` (before: the later row won silently). The fixtures here have none; check Earnie's catalog (`tariffs.json`) and existing user files before the next release Earnie picks up, and add the rule to the development document `Earnie-Benutzertarife-Entwicklungsdokument.md` so it matches spec section 3
- [ ] **Error in the monthly table names no row** — month 13 shows `Invalid value "13" for field "month"`; the page shortens the field path, so the user does not see which row is wrong. Show the row (or the `year-month`) in the message; regression test in `tests/test_ui_browser.py`
- [ ] **Browser tests not in CI** — `tests/test_ui_browser.py` runs only on request (`-m browser`). Decide with `0.1.r` whether a CI job with Chromium runs them (`pip install -e ".[ui,browser]"`, `python -m playwright install chromium`)
- [ ] **Browser tests not yet run on Windows** — verified only in the cloud container (Linux). The grid is driven by pixel positions (35 px rows), so display scaling or another Streamlit version may break it; run once locally (setup in skill `streamlit-apptest`)

## New Bugs (do not remove - even if empty)


## Minor improvements (do not remove - even if empty)
- [ ] The entry "Feiertage zählen" on 4. Erweitert can be removed - it's easier for user to include Feiertage in Zeitfenster for Sonntage
- [ ] Does it make sense to have "2. Zeitfenster" enabled for tariffs built on Börsenpreis? Check and remove

## Document Review Findings

Docs-only corrections (README, user docs, spec links). Skill `doc-review-findings`.
