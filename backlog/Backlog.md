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
- [ ] **Capacity charge AT 2027: verify against the SNE-T-V** — the SNE-G-V is final (BGBl. II Nr. 299/2026; monthly prices in cent per kW, bands split at 10 kW, minimum 2 kW on Netzebene 7; implemented in `0.1.q`). Still open until the SNE-T-V (consultation end of October 2026, final expected December 2026): prices and introduction date per grid area, whether the peak is billed in its own or the following month, whether § 34 (1) adds a contracted-power line for existing connections, and how customers without 15-minute values are billed; then fill the grid-fee catalog and set its `status`. Research note: Earnie `backlog/SNE-G-V-2027-Research.md`
- [ ] **14a-Atlas license** — may its data be used for a DE grid-fee catalog? Do not scrape until clarified
- [ ] **Shared library (weather)** — built in the Earnie repo as the standalone package `opendata` (Earnie *Edibert P6*, 2026-10-27): no Earnie imports, Open-Meteo archive and forecast, Energy-Charts `public_power` / `price`, one retry policy, disk cache for settled archive days. Open: own repository and PyPI name; whether Edibert's `MarketArchive` (Day-Ahead cache) moves onto it
- [ ] **License when Earnie contains the library** — PolyForm Noncommercial for Edibert versus Earnie's own license; as the owner a separate grant is possible; decide before both ship as one product
- [ ] **Editor technology** — headless form model plus Streamlit first (decided); later Home Assistant config flow or ingress page for stand-alone use

## Feature Backlog

### Version 0.1 — Engine, editor, contribution path

Mapping to the development document: T1 = `0.1.a`, T2 = `0.1.b`, T3 = `0.1.c`, T4/T4b = `0.1.d`.

- [ ] **0.1.d — Catalog: tariff database client and signed catalog packages** *(0.1.c done; re-cut 2026-10-29 after the business-model concept of 2026-10-28; legal questions assumed settled for planning, the legal review item stays open before anything is opened to users)*
  - **Model:** two databases. The *free database* holds user entries, unchecked, with the status `reliable` earned by use (a tariff version used by at least two installations within 12 months, the creator counts). The *verified database* holds only tariffs we checked, kept current, shipped as a signed package by subscription. The GitHub-issue contribution route is dropped, and contributions earn no reward. Edibert keeps format, package check and client public; the review workflow, the verified data, the signing key and the server are private and not part of this repository
  - **Builds on Earnie *Edibert P8* (decided 2026-10-28, Earnie `docs/dev/edibert-integration.md` § P8):** the public Earnie catalog (`tariffs.json`, `grid_fees.json`) is a frozen seed and the start of the verified database; new entries only through this channel. Catalog packages must bring the monthly rates of the reference curves; a package import must not overwrite monthly rows a user entered without telling
  - **Docs to the two-database model** (concept section 7): `catalog/README.md` (still says access by contribution or one-time fee), `README.md` / `README.de.md` and `CONTRIBUTING.md`: free database with `reliable` by use, verified database by subscription, no access by contribution, no GitHub-issue route
  - **Status (2026-10-29):** P1–P6 done ([Erledigt](Backlog-Erledigt.md)); open: P7 (P6 sends nothing until a transport exists), the docs bullet above, and the first real signing key in `edibert.package.TRUSTED_KEYS` (generated and kept privately)
  - **Order:** P1 → P2 → P3 → P4 → P5 is the verified-database path (acceptance: reference curves and one quarter of price changes reach users without editing `tariffs.json` by hand). P6 can run in parallel. P7 needs the exchange contract and the server
  - **Catalog P1 — tariff identity and version:** `tariff_identity(tariff)` gives a stable database ID from land, supplier, product, `area_id` (grid fees only) and direction. `tariff_version(tariff)` is a SHA-256 over the price-relevant fields in canonical JSON (sorted keys, normalised numbers; without `label`, `$comment`, `source`, `last_verified`, `behavior_notes`). Tests: the hash is stable under key order and comments and changes with every price change
  - **Catalog P2 — tariffs with validity versions** (prerequisite; takes over the `0.+1` item *Tariffs that change over time*): several entries with the same ID and `valid_from` / `valid_to` on whole days, no overlap, a date without an entry is an error, never skipped silently (same pattern as `capacity_charges`). Schema, spec sections 2a and 4a. Decided during implementation: `tariff_format` stays 1 (the fields are additive and optional, spec section 2a), so no migration
  - **Catalog P3 — origin on the user tariff:** `db_ref` (`database` = `free` / `verified`, `id`, `version`, `hash`), set on "copy from catalog"; the editor shows "differs from version X" when the hash no longer matches
  - **Catalog P4 — signed catalog package, format and check:** one file with a manifest (`package_format`, `database`, `issued_at`, `valid_until`, `tariff_format`, `key_id`, hashes of the content files) and the content (`tariffs.json`, `grid_fees.json` with the monthly rates of the reference curves), plus a signature checked offline. Proposal: Ed25519 via `cryptography`, public keys shipped in Edibert as a list by `key_id` so a key can be rotated (alternative named in the concept: Cosign/Sigstore). New errors `PACKAGE_SIGNATURE_INVALID`, `PACKAGE_KEY_UNKNOWN`, `PACKAGE_FORMAT_UNSUPPORTED`, `PACKAGE_CONTENT_MISMATCH`; `PACKAGE_EXPIRED` is a warning only, because the last received package may be used after a subscription ends. Edibert only verifies; signing runs in the private workflow, tests use a test key
  - **Catalog P5 — package import:** `package_import_plan(...)` lists new, changed and removed tariffs and the monthly rows that differ from local entries; such a conflict is never overwritten silently, the caller decides per conflict or the import fails. Applying replaces the catalog files atomically; `user_tariffs.json` stays untouched. CLI `python -m edibert package verify|import`, import dialog with preview in the editor, texts in both catalogs, spec and user manual (en, de)
  - **Catalog P6 — sharing client** (payload and UI need no server): `contribution_payload(tariff)` takes only whitelisted fields (no free text, no `behavior_notes`, no meter or consumption data); `individual` tariffs are always refused. Preview of the exact content before the first send, every tariff can be left out. The default comes from the embedding program as a required parameter of `ui/embed.py`: stand-alone Edibert shares by default, Earnie only after opt-in (concept decision 2026-10-29); a missing value is an error, never a silent default. Transport through a replaceable adapter; without a configured endpoint it stays off and says so
  - **Catalog P7 — exchange with the server** (contract first, as public spec `docs/spec/catalog-exchange.md`, analogous to Earnie `docs/workflow/usage-ping.md`). Principle: Edibert always computes locally and offline; the server only delivers and counts, so an outage never changes a price; exchange runs beside the calculation, with a hard off switch by environment variable. Five routes:
    - **Load package** (server → local): `GET /edibert/v1/packages/{free|verified}/latest`, `verified` with `Authorization: Bearer <access key>`; the file goes through P4 and P5. Weekly or when `valid_until` comes near; a manual download and import works the same way
    - **Submit tariff** (local → server): `POST /edibert/v1/tariffs` with the P6 payload, identity and version hash, without any installation ID; answer: database ID, version, `accepted` / `duplicate` / `rejected` with a code; the client then sets `db_ref`
    - **Report use** (local → server, daily): per used tariff version `{db_id, version, pseudonym}` with `pseudonym = HMAC(install_secret, db_id)` computed **on the client**; the secret never leaves the installation, so the server cannot link the tariffs of one installation. Not through Earnie's UsagePing, which carries the installation ID; a call of its own with its own consent in Earnie. One request per tariff with random delay against linking by connection (decide whether needed)
    - **Query status** (daily): `POST /edibert/v1/status` with a list of `{db_id, version}`, without any ID; per entry the newest version with `valid_from`, `reliable` and counters. Shown in the UI, as Home Assistant sensor attribute and in the MQTT topic
    - **Access key:** issued by the server after checking the subscription or Earnie Companion Cloud; stored locally as a secret
  - **Server side (private, not in this repository; proposal):** a process of its own next to the existing receivers behind the same reverse proxy, with SQLite (tariffs, versions, pseudonyms with last report date, moderation state, hashed access keys with expiry), a small web framework instead of the standard library (routing, auth, webhooks), packages as static files with the access key checked before delivery, a payment webhook, moderation first as a server CLI, rate limits. **The signing key never lives on the server**: it only holds signed files, so a compromised server cannot ship packages Edibert accepts
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
- [ ] **Capacity charge AT 2027 (class B, spec section 5b)** — monthly peak-based grid fee (SNE-G-V, per grid area from 2027); see Earnie development document "Leistungstarif AT 2027"; keep spec, development document and these items consistent
  - **Note:** the engine (loading, month amount, ladder, price-series block, CLI) is done in `0.1.q` ([Erledigt](Backlog-Erledigt.md)); the parts below build on it
  - Editor: capacity charge in the house settings (minimum, bands, validity, status); invoice check with "highest quarter hour of the month (kW)" and a `capacity_eur` line next to energy and fees; preview table "cost of one more kW of peak this month"
  - Publish: capacity block as Home Assistant sensor attributes (`capacity_free_up_to_kw`, `capacity_ladder`, `capacity_days_remaining`), month-to-date peak read from a configured entity (after `0.1.e`)
  - Comparison: monthly peaks and capacity cost from a logged 15-minute consumption file (with the "vector multiplication" item above); without a consumption file only as an explicitly entered assumed peak, marked `estimate`, never as a cent/kWh surcharge
  - Not in scope: Edibert as keeper of the monthly peak state; automatic conversion of the charge into cent/kWh
- [ ] Output formats for evcc, EMHASS, Predbat; price source from a Home Assistant entity (I3b)
- [ ] Import adapters: open-energy-tariffs, SmartGridready dynamic tariff (CH)
- [ ] DE grid-fee catalog (depends on data source and license)
- [ ] Tariffs that change over time (new prices from a date) *(left open from `0.1.g`)* — catalog side done in `0.1.d` Catalog P2; open: several validity versions of one **user** tariff (editor and `user_tariffs.json`, today `ID_COLLISION`)

## Findings from former Research

- **Note:** The Earnie backlog keeps a single item, *Edibert integration — use Edibert for tariffs*, that refers here. Engine, editor, catalog and publishers are tracked in this backlog; Earnie-side integration (replacing its own tariff resolution, embedding the editor, packaging) is tracked in the Earnie backlog.
