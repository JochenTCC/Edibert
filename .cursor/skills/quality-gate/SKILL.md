---
name: quality-gate
description: >-
  Runs the Edibert MINOR release quality / hardening gate (backlog chapter
  X.Y.r): coverage baseline, dead-code and obsolete-test audit, identify
  redundant or unnecessarily complex code without changing functionality, KPI
  refactor including mega-file splits, docs review, then a SonarCloud
  snapshot. Use when the user asks for a quality gate, release hardening, 0.1.r,
  or a coverage/KPI audit before an official release.
---

# Quality / release hardening gate

Canonical shape: **coverage → dead-code / obsolete tests → simplify (no behavior change) → KPI refactor (incl. mega-file splits) → docs → SonarCloud snapshot**. Do **not** tag, bump the version, or publish; that is [session-abschluss](../session-abschluss/SKILL.md).

Never auto-delete tests, fixtures, or vulture hits — triage with the user.

```
Quality gate:
- [ ] 1. Coverage baseline
- [ ] 2. Dead-code / obsolete-test audit
- [ ] 3. Redundant, unnecessarily complex, or unneeded code (no functional change)
- [ ] 4. KPI refactor — functions + files over hard limits
- [ ] 5. Docs (README, spec, examples vs the code)
- [ ] 6. SonarCloud snapshot
- [ ] 7. Record results in the open X.Y.r backlog chapter (do not bump the version)
```

Windows: UTF-8 env prefix (skill `windows-unicode-console`); PowerShell 5.x has no `&&`.

## 1. Coverage baseline

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; $env:PYTHONPATH='src'; python -m pytest --cov=. --cov-report=term-missing -q
```

Flag any module **< 40%** as a test gap (report only; not a CI failure). Record the overall line rate and per-module rates against the previous `.r`.

## 2. Dead-code / obsolete-test audit

Requires `pip install -e ".[dev]"`.

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -m vulture src tests --min-confidence 80
```

Triage the hits. Fail-fast tests for unsupported tariff features (`tiers`, `applies_to`, unknown fields) are intentional — keep them.

## 3. Redundant, unnecessarily complex, or unneeded code

List candidates **before** deleting or rewriting: duplicate helpers, wrappers that only forward, branches that always take one side, commented-out code, flags that no longer change results, tests that only re-assert another test.

Rules:

- **No functional change:** same public API, same price series, same JSON shapes.
- Propose a short triage list (file, what, why safe); apply only accepted items or clearly mechanical ones.
- Do not "simplify" by changing defaults, rounding, or fallbacks that alter prices.
- Re-run the smallest pytest set after each accepted change.

## 4. KPI refactor — do not defer mega-file splits

| KPI | Target | Hard limit |
|-----|--------|------------|
| Function body LOC (no blanks/comments/docstrings) | ≤ 40 | split before feature work if **> 60** |
| Module file LOC | ≤ 300 | **600** |
| Cyclomatic complexity / nesting | ≤ 10 / ≤ 3 | — |

Files over the hard limit and functions > 60 LOC are in-gate work. Split in bounded steps (≤ 3 files per step), keep import facades where callers rely on them, re-run pytest after each step. Ask only about order or API surface, not whether to skip.

## 5. Docs

`README.md` / `README.de.md`, `docs/user/en|de/`, `docs/spec/tariff-format.md`, `examples/`, `CONTRIBUTING.md` against the current code; translation catalogs complete in all languages (`tests/test_i18n_catalogs.py`) and every English user page has a German counterpart. Open findings that are not fixed go under `## Document Review Findings` in `backlog/Backlog-Bugfixes.md` (skill `doc-review-findings`). Check that no draft legal text slipped into the repo.

## 6. SonarCloud snapshot

CI scans `main` and pull requests (`.github/workflows/sonarcloud.yml`). **Do not** re-run Sonar or `pytest --cov` locally for this step. Open the SonarCloud project (`JochenTCC_Edibert`) on the `main` commit this `.r` is based on.

| Record | Rule |
|--------|------|
| Sonar Quality Gate | Passed / Failed — **informational** (not a required GitHub check) |
| New issues since last `.r` | Bugs, vulnerabilities, security hotspots only — **new**, not historical debt |
| Code smells | Triage like vulture; fix only what the user accepts |
| Coverage | Note the dashboard % vs the local baseline; do not chase alignment |

**Fail the `.r` chapter** only if there are **new bugs or vulnerabilities** on `main` that are not deferred with an explicit item in `backlog/Backlog-Bugfixes.md`.

## 7. Backlog — no version bump

Tick the open `X.Y.r` items in `backlog/Backlog.md` with measured numbers (pytest count, coverage, vulture hits, removals vs deferred, split files, Sonar status and new-issue counts). **Never** change the package version in this skill.

## Do not

- Defer mega-file splits to a later letter or `0.+1`
- Auto-delete tests/fixtures
- Change behavior while simplifying (defaults, numerics, APIs, persisted keys)
- Tag, publish, or bump the version
- Re-run Sonar locally or treat Sonar coverage as a second baseline
- Make the Sonar Quality Gate a required GitHub check from this skill
