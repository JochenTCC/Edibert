# Completed Items

Archive of completed work. Open todos → [Backlog.md](Backlog.md) · Bugfixes → [Backlog-Bugfixes.md](Backlog-Bugfixes.md).

### Language policy and multilingual foundation (2026-10-12)

- [x] **Language policy** — technical documents English only; README and user manuals in English (authoritative) and German (`README.de.md`, `docs/user/en|de/`); legal texts per country in the national language (DE/AT/CH: German); rule `docs-language.mdc` replaces `german-user-docs.mdc`
- [x] **Multilingual skeleton** — `edbert.i18n` (`Translator`, `en`/`de` catalogs), `edbert.errors` (`EdbertError`, `ErrorCode`), catalog parity tests, docs translation test, user manual placeholders

### Repository scaffold (2026-10-12)

- [x] **Repository scaffold** — local repo with README, `LICENSE` (PolyForm Noncommercial 1.0.0, verbatim) and `NOTICE`, contributing guide, format spec draft (`docs/spec/tariff-format.md`), four example tariffs, smoke tests, package skeleton `src/edbert/`
- [x] **Rules and skills ported from Earnie** — `.cursor/rules` (no-implicit-fallbacks, powershell-shell, german-user-docs (later replaced by docs-language), english-chat, versioning, backlog, roadmap-nomenclature, backlog-anonymize-users, edbert-project) and `.cursor/skills` (windows-unicode-console, bugfix-regression-test, doc-review-findings, session-abschluss, quality-gate)
- [x] **Draft legal texts moved out of the repo** — catalog terms, contribution terms, privacy notice and review checklist live in the Earnie project folder until legally reviewed
