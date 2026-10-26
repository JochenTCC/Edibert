# Earnie parity fixtures

Compatibility tests against Earnie (`tests/test_earnie_parity.py`, backlog `0.1.g`, shared with `0.1.r`).

| File | Content |
|---|---|
| `tariffs.json` | Excerpt of Earnie's catalog `share/config/tariffs.json` (`catalog_as_of` inside): the tariffs the fixtures price, plus the placeholder `parity_prior_month` (placeholder prices) for the prior-month fallback. |
| `grid_fees.json` | Excerpt of Earnie's `share/config/grid_fees.json`: areas `AT-VBG`, `AT-WIEN` and their rule set. |
| `expected_prices.json` | Earnie's committed P3a fixture (`tests/fixtures/edibert_parity/expected_prices.json` in Earnie), unchanged: 9 tariffs x 4 windows (DST spring 2026, month change with SNAP start, SNAP day, DST autumn 2025). |
| `monthly_fallback.json` | Earnie's prices on the edge months of the monthly tables (72-hour windows across a month change), the fallback Earnie took per month (`prior_year` / `prior_month`), or Earnie's error. |
| `make_fixture.py` | Regenerates all four with Earnie's engine (run from an Earnie checkout before Earnie P3b). |

**Unverified data.** The catalog excerpts are published supplier and grid-operator prices as Earnie's catalog holds them; they are not checked against the price sheets here and carry no personal data. They serve only as test input: both engines price the same input, so the values need not be current.

`netznutzung` for import cases is what Earnie writes into a house profile: `{area_id, power_metering: unmetered_power, quarter_hour_meter: true, include_status: [verordnet]}`. Day-ahead prices are the deterministic pattern of Earnie's harness (`epex_cent` per window, negative values included).

Known, triaged deviation **T1** (Earnie `docs/dev/edibert-integration.md`, P3a triage): on the autumn DST night Earnie averages both 02:00 hours for hourly settled spot tariffs; Edibert prices each real hour. The test asserts this difference explicitly.
