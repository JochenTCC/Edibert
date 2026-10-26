# Open Bugs

Completed items → [Backlog-Erledigt.md](Backlog-Erledigt.md) (sections `### Bugfix …` / `### Document Review …`)

Feature roadmap → [Backlog.md](Backlog.md)

## Classification

Group open bugs by topic chapters (`## Bug <Topic>`). Each code bugfix gets a regression test proposal (skill `bugfix-regression-test`).

## Bugfix Verifications Pending

Fix is implemented and committed, acceptance (real tariff check, Home Assistant test, reporter confirmation) is outstanding. Do not archive before acceptance.

- [ ] **Gross tariff: net grid fee added without VAT** *(fixed in 0.1.i, 2026-10-26)* — `tariff.evaluate` added the net grid fee to a gross supplier price without VAT (30 ct + 8 ct = 38 ct instead of 39.6 ct at 20 %); Earnie puts the VAT on it (`grid_fee_on_tariff_basis`). Now: gross prices get `grid_fee * (1 + vat_percent/100)`, net prices `(supplier + grid fee) * (1 + vat_percent/100)`; `vat_cent` of a gross price point is the VAT on the grid fee. Affects editor preview, invoice check and the MQTT publisher. Regression test: `tests/test_grid_fee_vat_regression.py`. Acceptance: Earnie P3a comparison against Earnie's engine with a gross tariff and a grid fee

## New Bugs (do not remove - even if empty)

## Minor improvements (do not remove - even if empty)
- [ ] The entry "Feiertage zählen" on 4. Erweitert can be removed - it's easier for user to include Feiertage in Zeitfenster for Sonntage
- [ ] Does it make sense to have "2. Zeitfenster" enabled for tariffs built on Börsenpreis? Check and remove

## Document Review Findings

Docs-only corrections (README, user docs, spec links). Skill `doc-review-findings`.
