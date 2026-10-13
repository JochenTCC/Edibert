# Project Roadmap & Backlog

Completed items → [Backlog-Erledigt.md](Backlog-Erledigt.md)

Open bugfixes → [Backlog-Bugfixes.md](Backlog-Bugfixes.md)

Spec: [`docs/spec/tariff-format.md`](../docs/spec/tariff-format.md). Internal development document (Earnie project folder): `Entwicklungsplan/Offen/Earnie-Benutzertarife-Entwicklungsdokument.md`. Draft legal texts: `Entwicklungsplan/Offen/Edbert-Bedingungstexte/`.

## Research Items

- [ ] **Name and trademark clearance** *(deferred)* — register searches (EUIPO TMview, DPMAregister, Austrian Patent Office) for "Edbert" and "Earnie", classes software, energy, services; domains (`edbert.de/.at/.com` are in use; `.ch/.eu/.io/.app/.energy/.dev` showed no DNS entry on 2026-10-12). Details are kept in the internal legal review checklist.
- [ ] **Legal review of the draft texts** — catalog terms, contribution terms, privacy notice, checklist in the Earnie project folder; decide on code-contribution consent (CLA) so a commercial license stays possible
- [ ] **Verify test fixtures against real price sheets** — Octopus Go / dynamicOctopus offer for the own postal code, Westnetz / EWR Netz / e-netz Südhessen / N-ERGIE §14a Modul 3 sheets (do they differ on weekends and holidays?)
- [ ] **Legal texts per country** — separate versions for Germany, Austria and Switzerland, each in the national language (German for all three); which version binds consumers; the current drafts are Austria-oriented
- [ ] **HACS publishing requirements** — no license requirement found in the docs; check default-store CI checks (brands, manifest, info) before any HACS release
- [ ] **Capacity charge AT 2027: verify against the final regulation** — the SNE-G-V and the per-area SNE-V 2027 are drafts as of 2026-10; confirm the billing formula (EUR/kW/year ÷ 12 × monthly peak?), the minimum (2 kW or 20 % of contracted power), the 10 kW band limit, the introduction date per grid area and whether opt-out customers are billed on the measured peak; then update spec section 5b and the grid-fee catalog `status`
- [ ] **14a-Atlas license** — may its data be used for a DE grid-fee catalog? Do not scrape until clarified
- [ ] **Shared library (weather)** — built when the forecast plug-in needs it; location open (proposal: standalone package without Earnie imports in the Earnie repo first, own repository later); no shared cache building block in advance
- [ ] **License when Earnie contains the library** — PolyForm Noncommercial for Edbert versus Earnie's own license; as the owner a separate grant is possible; decide before both ship as one product
- [ ] **Editor technology** — headless form model plus Streamlit first (decided); later Home Assistant config flow or ingress page for stand-alone use

## Feature Backlog

### Version 0.1 — Engine, editor, contribution path

Mapping to the development document: T1 = `0.1.a`, T2 = `0.1.b`, T3 = `0.1.c`, T4/T4b = `0.1.d`.

- [ ] **0.1.d — Catalog: contribution path and signed catalog access** *(0.1.c done; legal review first)*
  - Catalog P1: opt-in upload with payload preview per tariff, `individual` flag, no free text and no personal data; GitHub-issue route first
  - **Note:** Edbert and the catalogue are free — donations are highly welcome; regular reminders may appear on running installations
  - **Note:** Use GitHub issues if a concrete tariff can't be modeled with the existing version
- [ ] **0.1.f — Library API and layering** *(architecture decision 2026-10-12, [`docs/spec/architecture.md`](../docs/spec/architecture.md))*
  - Public facade `edbert.api` (few functions, versioned) for Earnie and other callers
  - Test: library modules never import `edbert.ui` or `edbert.publish`
  - Split `build_forecaster` / `load_forecaster`: the library takes a forecaster object; the key check belongs to the plug-in loader of the product
- [ ] **0.1.g — Tariff supply for the past and the future**
  - Monthly-table fallback as in Earnie (exact → same month previous year → previous month) with a coded warning `MONTH_RATE_FALLBACK`, also when the 72-hour window reaches a month change
  - Price points carry `market_cent` and the forecast method (`exact`, `mirror`, `hold`, plug-in name)
  - Market prices for arbitrary ranges (simulation/backtesting) with a long-range cache, ported from Earnie (`live_price_cache`, backtesting prices), no pandas
  - Evaluation of past periods with Earnie's tolerance rules; committed compatibility tests against Earnie results (shared with `0.1.r`)
  - Later: tariffs that change over time (new prices from a date)
- [ ] **0.1.e2 — Publish: native Home Assistant integration** *(0.1.e done)*
  - Publish P1: HA custom integration (sensor with `raw_today` / `raw_tomorrow` / `forecast`, action `get_rates(start, end, resolution)`), reading the same price series as the MQTT publisher
  - Clean up retained topics of tariffs removed from `publish.json`
  - Earnie's OLS model is handed in as a forecaster object (no key); the key only guards plug-ins loaded through entry points; decide how keys are issued and checked
- [ ] **0.1.r — Quality / release hardening** *(skill `quality-gate`; after 0.1.a–0.1.e)*
  - Coverage baseline, dead-code audit, simplification, KPI refactor, docs review, SonarCloud snapshot
- [ ] **0.1.0 — Release** *(user decision; version bump only with approval)*

### Version 0.+1

- [ ] Simple "vector multiplication" of a selected tariff and a logged consumption file for primitive comparison of tariffs (only with hint to Earnie SE)
- [ ] Graphical comparison of multiple tariffs without consumption
- [ ] Tiers and free allowances (class B)
- [ ] **Capacity charge AT 2027 (class B, draft spec section 5b)** — monthly peak-based grid fee (SNE-G-V, per grid area from 2027); see Earnie development document "Leistungstarif AT 2027"; keep spec, development document and these items consistent
  - Engine: `capacity_charges` in the house profile and in `grid_fees.json` (bands, `min_kw`, validity, `status`), strict loading, `include_status` filter, convexity warning; `capacity_charge_eur` (month amount) and `capacity_ladder` (remaining cost relative to the month-to-date peak, stateless, state from the caller, never guessed); `capacity` block in `PriceSeries.to_dict()` per calendar month; CLI `python -m edbert capacity --peak-so-far … --power …`; new error and warning codes with texts in both catalogs; schema regenerated
  - Editor: capacity charge in the house settings (minimum, bands, validity, status); invoice check with "highest quarter hour of the month (kW)" and a `capacity_eur` line next to energy and fees; preview table "cost of one more kW of peak this month"
  - Publish: capacity block as Home Assistant sensor attributes (`capacity_free_up_to_kw`, `capacity_ladder`, `capacity_days_remaining`), month-to-date peak read from a configured entity (after `0.1.e`)
  - Comparison: monthly peaks and capacity cost from a logged 15-minute consumption file (with the "vector multiplication" item above); without a consumption file only as an explicitly entered assumed peak, marked `estimate`, never as a cent/kWh surcharge
  - Not in scope: Edbert as keeper of the monthly peak state; automatic conversion of the charge into cent/kWh
- [ ] Output formats for evcc, EMHASS, Predbat; price source from a Home Assistant entity (I3b)
- [ ] Import adapters: open-energy-tariffs, SmartGridready dynamic tariff (CH)
- [ ] DE grid-fee catalog (depends on data source and license)

## Findings from former Research

- **Note:** The Earnie backlog keeps a single item, *Edbert integration — use Edbert for tariffs*, that refers here. Engine, editor, catalog and publishers are tracked in this backlog; Earnie-side integration (replacing its own tariff resolution, embedding the editor, packaging) is tracked in the Earnie backlog.
