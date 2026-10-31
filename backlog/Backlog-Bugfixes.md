# Open Bugs

Completed items → [Backlog-Erledigt.md](Backlog-Erledigt.md) (sections `### Bugfix …` / `### Document Review …`)

Feature roadmap → [Backlog.md](Backlog.md)

## Classification

Group open bugs by topic chapters (`## Bug <Topic>`). Each code bugfix gets a regression test proposal (skill `bugfix-regression-test`).

## Bugfix Verifications Pending

Fix is implemented and committed, acceptance (real tariff check, Home Assistant test, reporter confirmation) is outstanding. Do not archive before acceptance.

## New Bugs (do not remove - even if empty)

- [ ] **Editor hint on missing months is stale** *(found in Earnie P7 S1, 2026-10-27)* — `ui.monthly_hint` (en, de) says a missing month stops the calculation; since `0.1.g` a missing month uses the prior-year / prior-month rate with the warning `MONTH_RATE_FALLBACK`, and only a table without any usable month fails (`PRICE_MISSING`). Fix both catalogs; regression test: catalog text check in `tests/test_i18n_catalogs.py` or a UI test that the monthly step shows the fallback wording.

## Minor improvements (do not remove - even if empty)
- [ ] The entry "Feiertage zählen" on 4. Erweitert can be removed - it's easier for user to include Feiertage in Zeitfenster for Sonntage
- [ ] Does it make sense to have "2. Zeitfenster" enabled for tariffs built on Börsenpreis? Check and remove

## Document Review Findings

Docs-only corrections (README, user docs, spec links). Skill `doc-review-findings`.
