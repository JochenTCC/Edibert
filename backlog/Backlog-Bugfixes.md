# Open Bugs

Completed items → [Backlog-Erledigt.md](Backlog-Erledigt.md) (sections `### Bugfix …` / `### Document Review …`)

Feature roadmap → [Backlog.md](Backlog.md)

## Classification

Group open bugs by topic chapters (`## Bug <Topic>`). Each code bugfix gets a regression test proposal (skill `bugfix-regression-test`).

## Bugfix Verifications Pending

Fix is implemented and committed, acceptance (real tariff check, Home Assistant test, reporter confirmation) is outstanding. Do not archive before acceptance.

- [ ] **New tariff kept the step of the previous one** *(found by the field-by-field AppTests, 2026-11-22)* — `state.adopt()` reset `ui.step` but not the step radio's own widget value, so "New" while in step 4 opened the new tariff in step 4. Fix: `adopt()` drops the radio key (`state.STEP_RADIO`), the radio starts at step 1 again. Test `tests/test_ui_editing.py::test_new_tariff_starts_at_step_one`. Acceptance: in the browser, open step 4, click "New import tariff", step 1 is shown.
- [ ] **Unknown timezone in house.json silently replaced** *(found by the field-by-field AppTests, 2026-11-22)* — the house timezone selectbox fell back to the first list entry (`Europe/Vienna`) for a value not in `COMMON_TIMEZONES`, without a message, and the next house save overwrote the file (against `no-implicit-fallbacks.mdc`). Fix: the saved value stays an option and an invalid one shows the coded error in the sidebar. Test `tests/test_ui_editing.py::test_unknown_timezone_in_house_file_is_reported_not_thrown`. Acceptance: in the browser, a typed-in valid zone outside the list stays, an invalid one shows the error. Region and power-metering selectboxes use the same `_index` fallback; not changed here.

## New Bugs (do not remove - even if empty)

- [ ] **Editor hint on missing months is stale** *(found in Earnie P7 S1, 2026-10-27)* — `ui.monthly_hint` (en, de) says a missing month stops the calculation; since `0.1.g` a missing month uses the prior-year / prior-month rate with the warning `MONTH_RATE_FALLBACK`, and only a table without any usable month fails (`PRICE_MISSING`). Fix both catalogs; regression test: catalog text check in `tests/test_i18n_catalogs.py` or a UI test that the monthly step shows the fallback wording.

## Minor improvements (do not remove - even if empty)
- [ ] The entry "Feiertage zählen" on 4. Erweitert can be removed - it's easier for user to include Feiertage in Zeitfenster for Sonntage
- [ ] Does it make sense to have "2. Zeitfenster" enabled for tariffs built on Börsenpreis? Check and remove

## Document Review Findings

Docs-only corrections (README, user docs, spec links). Skill `doc-review-findings`.
