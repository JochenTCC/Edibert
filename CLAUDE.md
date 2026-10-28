# CLAUDE.md — Edibert

Tariff editor and price service. Draft stage: format spec and examples exist, no engine yet.

Project rules live in `.cursor/rules/*.mdc` and `.cursor/skills/*/SKILL.md` (written for Cursor, same layout as the Earnie repo). They apply to Claude Code too: read the matching rule before acting in its area. This file only lists the essentials and points there.

## Rules and skills

| File | Topic |
|---|---|
| `.cursor/rules/edibert-project.mdc` | Guardrails: license, legal drafts, no real data, tariff semantics |
| `.cursor/rules/no-implicit-fallbacks.mdc` | Fail loud instead of silent fallbacks |
| `.cursor/rules/powershell-shell.mdc` | PowerShell 5.x syntax (no `&&`) |
| `.cursor/rules/docs-language.mdc` | Technical docs English only; user manuals EN+DE (English authoritative); UI via translation catalogs; legal texts per country in the national language |
| `.cursor/rules/versioning.mdc` | Version bumps only with explicit approval |
| `.cursor/rules/english-chat.mdc` | Cursor chat language (English). **Claude Code follows the section below** |
| `.cursor/rules/backlog.mdc` | Backlog files, bugfix lifecycle, archive format |
| `.cursor/rules/roadmap-nomenclature.mdc` | Version letters, epics/phases/steps, commit syntax |
| `.cursor/rules/backlog-anonymize-users.mdc` | Scrub personal names in the bugfix/archive files before commit |
| `.cursor/rules/streamlit-ui-state.mdc` | Editor state: language-independent versioned keys, row uids, callbacks |
| `.cursor/skills/streamlit-apptest/` | Headless AppTest tests of the editor |
| `.cursor/skills/windows-unicode-console/` | UTF-8 env for Python on Windows |
| `.cursor/skills/bugfix-regression-test/` | Propose a regression test after each bugfix |
| `.cursor/skills/doc-review-findings/` | Process `## Document Review Findings` |
| `.cursor/skills/session-abschluss/` | End of session: backlog sync, commit, push, publish decision (lean) |
| `.cursor/skills/quality-gate/` | `X.Y.r` release hardening incl. SonarCloud snapshot |

Not ported from Earnie (Earnie-specific): test-health scripts, branching playbook, EHAL rules, Docker hooks, release promote job.

## Backlog

`backlog/Backlog.md` (open features, `0.1.a`… up to `0.1.r` and release `0.1.0`), `backlog/Backlog-Bugfixes.md`, `backlog/Backlog-Erledigt.md`. Backlog files are **English**. Mapping to the development document: T1 = `0.1.a`, T2 = `0.1.b`, T3 = `0.1.c`, T4/T4b = `0.1.d`.

## SonarCloud

CI scans `main` and pull requests (`.github/workflows/sonarcloud.yml`, `sonar-project.properties`, project key `JochenTCC_Edibert`). It needs a SonarCloud project and a `SONAR_TOKEN` repository secret, which the user sets up; do not create or change either. Local runs do not call Sonar. The snapshot is part of the quality gate skill.

## Tests

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'
$env:PYTHONPATH='src'; python -m pytest -q
```

UTF-8 env is required on Windows (see skill `windows-unicode-console`).

Browser tests of the monthly-rate table (opt-in, Playwright): `python -m pytest -m browser tests/test_ui_browser.py` (setup in skill `streamlit-apptest`).

## Shell

Windows PowerShell 5.x: no `&&` / `||` (`.cursor/rules/powershell-shell.mdc`). In the Bash tool (Git Bash) POSIX syntax is fine.

## Chat language

Reply in **German** in Claude Code chat (the user switches language spontaneously when needed; follow that). `.cursor/rules/english-chat.mdc` applies to Cursor only. Commit messages, spec, code, issues, and all technical documents stay English. User manuals and the README exist in English (authoritative) and German (`docs-language.mdc`). Legal texts are written per country in the national language, outside this repo until reviewed.

## Versioning and publishing

- **Never change the version** (`pyproject.toml`, `src/edibert/__init__.py`) without explicit user approval; propose and ask (`versioning.mdc`).
- Do not commit, push, tag, or publish unless asked.

## Code changes

- **No silent fallbacks:** unsupported tariff features (`tiers`, `applies_to` other than `"main"`, unknown fields) must fail loudly, never be ignored (`no-implicit-fallbacks.mdc`).
- Spec: `docs/spec/tariff-format.md` (English), derived from the internal development document `Earnie-Benutzertarife-Entwicklungsdokument.md` in the Earnie project folder; keep both consistent.
- Never commit real customer data, addresses, meter numbers, or invoice files. Examples use placeholder prices.

## Legal

- `LICENSE` is the verbatim PolyForm Noncommercial 1.0.0 text and must not be edited.
- Draft legal texts (catalog terms, contribution terms, privacy notice, review checklist) are **not in this repo**. They live in the Earnie project folder under `Entwicklungsplan/Offen/Edibert-Bedingungstexte/` until legally reviewed. Do not re-add them here and do not describe them as final.
