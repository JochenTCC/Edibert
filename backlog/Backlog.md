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
- [ ] **14a-Atlas license** — may its data be used for a DE grid-fee catalog? Do not scrape until clarified
- [ ] **Editor technology** — headless form model plus Streamlit first (decided); later Home Assistant config flow or ingress page for stand-alone use

## Feature Backlog

### Version 0.1 — Engine, editor, contribution path

Mapping to the development document: T1 = `0.1.a`, T2 = `0.1.b`, T3 = `0.1.c`, T4/T4b = `0.1.d`.

- [ ] **0.1.d — Catalog: contribution path and signed catalog access** *(0.1.c done; legal review first)*
  - Catalog P1: opt-in upload with payload preview per tariff, `individual` flag, no free text and no personal data; GitHub-issue route first
  - Catalog P2: signed catalog package with validity date, manual import; credit for accepted contributions or small one-time fee
  - Catalog P3 (later): automatic updates / yearly subscription
- [ ] **0.1.e — Publish: Home Assistant sensor and MQTT** *(0.1.b done)*
  - Publish P1: HA sensor with `raw_today` / `raw_tomorrow` and `forecast`, action `get_rates(start, end, resolution)`
  - Publish P2: MQTT (retained, HA discovery)
- [ ] **0.1.r — Quality / release hardening** *(skill `quality-gate`; after 0.1.a–0.1.e)*
  - Coverage baseline, dead-code audit, simplification, KPI refactor, docs review, SonarCloud snapshot
- [ ] **0.1.0 — Release** *(user decision; version bump only with approval)*

### Version 0.+1

- [ ] Price per meter / consumer (`applies_to`), e.g. heat-pump meter or EV allowance (class B/C; needs consumer-aware consumers such as Earnie)
- [ ] Tiers and free allowances (class B), capacity charge (see Earnie development document "Leistungstarif AT 2027")
- [ ] Rule condition from an external signal (Home Assistant entity state), e.g. provider events (class C)
- [ ] Manual price overrides (time-limited promotions, `source: manual_override`)
- [ ] Price sheet assistant (PDF/photo → proposal, user confirms, invoice check)
- [ ] Output formats for evcc, EMHASS, Predbat; price source from a Home Assistant entity (I3b)
- [ ] Import adapters: open-energy-tariffs, SmartGridready dynamic tariff (CH)
- [ ] DE grid-fee catalog (depends on data source and license)

## Findings from former Research

- **Note:** The Earnie backlog keeps a single item, *Edbert integration — use Edbert for tariffs*, that refers here. Engine, editor, catalog and publishers are tracked in this backlog; Earnie-side integration (replacing its own tariff resolution, embedding the editor, packaging) is tracked in the Earnie backlog.
