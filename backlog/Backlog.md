# Project Roadmap & Backlog

Completed items → [Backlog-Erledigt.md](Backlog-Erledigt.md)

Open bugfixes → [Backlog-Bugfixes.md](Backlog-Bugfixes.md)

Spec: [`docs/spec/tariff-format.md`](../docs/spec/tariff-format.md). Internal development document (Earnie project folder): `Entwicklungsplan/Offen/Earnie-Benutzertarife-Entwicklungsdokument.md`. Draft legal texts: `Entwicklungsplan/Offen/Edibert-Bedingungstexte/`.

## Research Items

- [ ] **Name and trademark clearance** *(deferred)* — register searches (EUIPO TMview, DPMAregister, Austrian Patent Office) for "Edibert" and "Earnie", classes software, energy, services; domains (`edibert.de/.at/.com` are in use; `.ch/.eu/.io/.app/.energy/.dev` showed no DNS entry on 2026-10-12). Details are kept in the internal legal review checklist.
- [ ] **Legal review of the draft texts** — catalog terms, contribution terms, privacy notice, checklist in the Earnie project folder; decide on code-contribution consent (CLA) so a commercial license stays possible
- [ ] **Verify test fixtures against real price sheets** — Octopus Go / dynamicOctopus offer for the own postal code, Westnetz / EWR Netz / e-netz Südhessen / N-ERGIE §14a Modul 3 sheets (do they differ on weekends and holidays?)
- [ ] **Legal texts per country** — separate versions for Germany, Austria and Switzerland, each in the national language (German for all three); which version binds consumers; the current drafts are Austria-oriented
- [ ] **HACS publishing requirements** — no license requirement found in the docs; check default-store CI checks (brands, manifest, info) before any HACS release
- [ ] **Capacity charge AT 2027: verify against the final regulation** — the SNE-G-V and the per-area SNE-V 2027 are drafts as of 2026-10; confirm the billing formula (EUR/kW/year ÷ 12 × monthly peak?), the minimum (2 kW or 20 % of contracted power), the 10 kW band limit, the introduction date per grid area and whether opt-out customers are billed on the measured peak; then update spec section 5b and the grid-fee catalog `status`
- [ ] **14a-Atlas license** — may its data be used for a DE grid-fee catalog? Do not scrape until clarified
- [ ] **Shared library (weather)** — built in the Earnie repo as the standalone package `opendata` (Earnie *Edibert P6*, 2026-10-27): no Earnie imports, Open-Meteo archive and forecast, Energy-Charts `public_power` / `price`, one retry policy, disk cache for settled archive days. Open: own repository and PyPI name; whether Edibert's `MarketArchive` (Day-Ahead cache) moves onto it
- [ ] **License when Earnie contains the library** — PolyForm Noncommercial for Edibert versus Earnie's own license; as the owner a separate grant is possible; decide before both ship as one product
- [ ] **Editor technology** — headless form model plus Streamlit first (decided); later Home Assistant config flow or ingress page for stand-alone use

## Feature Backlog

### Version 0.1 — Engine, editor, contribution path

Mapping to the development document: T1 = `0.1.a`, T2 = `0.1.b`, T3 = `0.1.c`, T4/T4b = `0.1.d`.

- [ ] **0.1.d — Catalog: contribution path and signed catalog access** *(0.1.c done; legal review first)*
  - **Builds on Earnie *Edibert P8* (decided 2026-10-28, Earnie `docs/dev/edibert-integration.md` § P8):** the public Earnie catalog (`tariffs.json`, `grid_fees.json`) is a frozen seed, new entries only through this channel; contribution terms: Edibert's own terms (README § License, after legal review) are the basis; Earnie `LICENSE.md` § 3 (4–8, draft) covers contributions from within Earnie until then; no contribution reward. Catalog packages must bring the monthly rates of the reference curves; a package import must not overwrite monthly rows a user entered in the site copy without telling
  - Catalog P1: opt-in upload with payload preview per tariff, `individual` flag, no free text and no personal data; GitHub-issue route first
  - **Note:** Edibert and the catalogue are free — donations are highly welcome; regular reminders may appear on running installations
  - **Note:** Use GitHub issues if a concrete tariff can't be modeled with the existing version
- [ ] **0.1.e2 — Publish: native Home Assistant integration** *(0.1.e done)*
  - Publish P1: HA custom integration (sensor with `raw_today` / `raw_tomorrow` / `forecast`, action `get_rates(start, end, resolution)`), reading the same price series as the MQTT publisher
  - Clean up retained topics of tariffs removed from `publish.json`
  - Forecast keys: the key only guards plug-ins loaded through entry points; decide how keys are issued and checked. (Earnie's OLS model runs as an in-process forecaster object without a key since Earnie *Edibert P5*, 2026-10-27; it uses `api.Forecaster` and the free mirror, no Edibert change was needed.)
- [ ] **0.1.h — Editor: persistence and logic tests for the embedded editor** *(after the Edibert integration in Earnie, Earnie *Edibert P7*; test concept "Earnie UI-Persistenztests"; split decided 2026-10-27, Earnie `docs/dev/edibert-integration.md` § P7 D1)*
  - Edibert owns the **editor** (authoring `user_tariffs.json`); the per-scenario **selection** (land / type filter, pick, own fixed price, next-month warning, planning clock, scenario switch) stays in Earnie, because its parts are Earnie concepts. Cases TE1–TE3, TE5 and TE6 therefore belong to Earnie's UI suite, not here:
    - **TE1 filter vs. selection**, **TE2 profile switch**, **TE3 own fixed price**, **TE5 month boundary**, **TE6 scenario switch** → Earnie (AppTest of the Szenarienkonfigurator)
  - Edibert keeps the editor cases: **TE4** file side (the next month of a monthly table is written to `user_tariffs.json`; model level, because AppTest cannot drive `st.data_editor`) and the save-path checks (rejected input shows an error and leaves the file unchanged; the success notice survives `st.rerun()`; stable language-independent widget keys). Covered by `0.1.m` (`tests/test_ui_embed.py`); open: a browser check of the monthly-rate table (with `0.1.r`)
- [ ] **0.1.r — Quality / release hardening** *(skill `quality-gate`; after 0.1.a–0.1.e)*
  - Coverage baseline, dead-code audit, simplification, KPI refactor, docs review, SonarCloud snapshot
- [ ] **0.1.0 — Release** *(user decision; version bump only with approval)*

### Version 0.+1

- [ ] Simple "vector multiplication" of a selected tariff and a logged consumption file for primitive comparison of tariffs (only with hint to Earnie SE)
- [ ] **Graphical comparison of multiple tariffs without consumption** *(scope extended by the dogfooding findings of 2026-10-28)*
  - Selection: "My tariffs" become selectable, so several tariffs show in the price preview at once; only one tariff stays open for editing
  - Time span: tariffs that differ by weekday switch the preview to a time axis over the days instead of 0–24 h; when only workday, Saturday and Sunday differ, Friday to Sunday is enough, otherwise a whole week. A market-price tariff needs one day. With several tariffs the widest span of all wins. A tariff with a holiday rule gets a fictitious holiday appended after Sunday
  - Colours and lines: colours tell the tariffs apart, no longer the days; import prices solid, export prices dashed (as in the Earnie monitor)
- [ ] Tiers and free allowances (class B)
- [ ] **Capacity charge AT 2027 (class B, draft spec section 5b)** — monthly peak-based grid fee (SNE-G-V, per grid area from 2027); see Earnie development document "Leistungstarif AT 2027"; keep spec, development document and these items consistent
  - Engine: `capacity_charges` in the house profile and in `grid_fees.json` (bands, `min_kw`, validity, `status`), strict loading, `include_status` filter, convexity warning; `capacity_charge_eur` (month amount) and `capacity_ladder` (remaining cost relative to the month-to-date peak, stateless, state from the caller, never guessed); `capacity` block in `PriceSeries.to_dict()` per calendar month; CLI `python -m edibert capacity --peak-so-far … --power …`; new error and warning codes with texts in both catalogs; schema regenerated
  - Editor: capacity charge in the house settings (minimum, bands, validity, status); invoice check with "highest quarter hour of the month (kW)" and a `capacity_eur` line next to energy and fees; preview table "cost of one more kW of peak this month"
  - Publish: capacity block as Home Assistant sensor attributes (`capacity_free_up_to_kw`, `capacity_ladder`, `capacity_days_remaining`), month-to-date peak read from a configured entity (after `0.1.e`)
  - Comparison: monthly peaks and capacity cost from a logged 15-minute consumption file (with the "vector multiplication" item above); without a consumption file only as an explicitly entered assumed peak, marked `estimate`, never as a cent/kWh surcharge
  - Not in scope: Edibert as keeper of the monthly peak state; automatic conversion of the charge into cent/kWh
- [ ] Output formats for evcc, EMHASS, Predbat; price source from a Home Assistant entity (I3b)
- [ ] Import adapters: open-energy-tariffs, SmartGridready dynamic tariff (CH)
- [ ] DE grid-fee catalog (depends on data source and license)
- [ ] Tariffs that change over time (new prices from a date) *(left open from `0.1.g`)*

## Findings from former Research

- **Note:** The Earnie backlog keeps a single item, *Edibert integration — use Edibert for tariffs*, that refers here. Engine, editor, catalog and publishers are tracked in this backlog; Earnie-side integration (replacing its own tariff resolution, embedding the editor, packaging) is tracked in the Earnie backlog.
