# Open Bugs

Completed items → [Backlog-Erledigt.md](Backlog-Erledigt.md) (sections `### Bugfix …` / `### Document Review …`)

Feature roadmap → [Backlog.md](Backlog.md)

## Classification

Group open bugs by topic chapters (`## Bug <Topic>`). Each code bugfix gets a regression test proposal (skill `bugfix-regression-test`).

## Bugfix Verifications Pending

Fix is implemented and committed, acceptance (real tariff check, Home Assistant test, reporter confirmation) is outstanding. Do not archive before acceptance.

- [ ] **Share section: server rejection without a reason** *(found in manual test of 0.1.d Catalog P7, 2026-10-30)* — the share section only shows "{rejected} rejected"; the server's `code` reaches `SendResult.code` but `ui/share.py` drops it. Seen with a tariff without `land`: valid locally, so it gets a checkbox, but the server rejects it (`TARIFF_INVALID`, no land means no database ID). Same area: `ServerTransport.send` never sends `based_on` although the tariff has a `db_ref` (contract `docs/spec/catalog-exchange.md` § 2), so a changed shared tariff starts a new entry instead of a new version. Fix: name every rejected tariff with its translated reason; refuse a tariff without `land` locally (`CONTRIBUTION_LAND_MISSING`, no checkbox); transport gets the `db_ref`. Regression tests: `tests/test_contribution.py` (land refusal, db_ref reaches the transport, rejection message per tariff), `tests/test_exchange.py` (`based_on` in the request body).
  - **Fix (0.1.10, 2026-10-30):** every rejected tariff is named with its translated reason; a tariff without `land` is refused locally (`CONTRIBUTION_LAND_MISSING`, no checkbox); the transport sends `based_on` from the `db_ref`. Regression tests in `tests/test_contribution.py` and `tests/test_exchange.py`.
  - **Tracker:** check live in the editor: a tariff without land has no checkbox, a server rejection names its reason, sharing a changed shared tariff gives a new version of the same entry.

## New Bugs (do not remove - even if empty)

- [ ] **Editor hint on missing months is stale** *(found in Earnie P7 S1, 2026-10-27)* — `ui.monthly_hint` (en, de) says a missing month stops the calculation; since `0.1.g` a missing month uses the prior-year / prior-month rate with the warning `MONTH_RATE_FALLBACK`, and only a table without any usable month fails (`PRICE_MISSING`). Fix both catalogs; regression test: catalog text check in `tests/test_i18n_catalogs.py` or a UI test that the monthly step shows the fallback wording.

## Minor improvements (do not remove - even if empty)
- [ ] The entry "Feiertage zählen" on 4. Erweitert can be removed - it's easier for user to include Feiertage in Zeitfenster for Sonntage
- [ ] Does it make sense to have "2. Zeitfenster" enabled for tariffs built on Börsenpreis? Check and remove

## Document Review Findings

Docs-only corrections (README, user docs, spec links). Skill `doc-review-findings`.

- [ ] **Editor manual: where catalog tariffs come from** *(found in manual test of 0.1.d Catalog P7, 2026-10-30)* — `docs/user/{en,de}/editor.md` § tool row: **Copy catalog tariff** copies from the local catalog files only. The manual does not say that tariffs of the free database (including shared ones) reach the local catalog only through a signed catalog package (`exchange fetch`, then `package import`, see `cli.md`), and that a shared tariff appears there only once a published package contains it. Add one sentence with a link to `cli.md` § catalog package; drop it again when the package download from the editor sidebar (0.1.d Catalog P7, client follow-ups) is built.
