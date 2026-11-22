---
name: bugfix-regression-test
description: >-
  Hard rule: every code bugfix comes with at least one new regression test that
  fails on the unfixed code and passes with the fix, in the same commit (prefer a
  dedicated regression file; cite the GitHub issue when available). Use when implementing a bugfix, fixing a GitHub issue, or when a
  wrong tariff price, rule match, holiday handling, or price series is found.
---

# Bugfix regression test

**Hard gate** (decided 2026-11-22, same rule in Earnie and earnie-server, `earnie-workspace/ai/ECOSYSTEM.md` § Hard rules): a bug found outside the automated tests (by hand, in the browser, in a log, by a user or a review) is fixed **only together with** at least one new automated test that fails on the unfixed code and passes with the fix. Fix and test land in the **same commit**; a fix without its test is not committed and not moved to Verifications Pending.

## Exceptions (the only ones)

State the exception in chat **and** in the backlog entry; do not invent a worthless test.

| Exception | Action |
|-----------|--------|
| Docs-only change | skip |
| Pure config / environment mistake with **no** wrong code path | reason in the backlog entry; skip |
| No automated test can reach the failing path | reason in the backlog entry; test the nearest reachable unit instead if one exists |

Anything else needs the user's explicit decision in chat to skip the test; note that decision in the backlog entry. Do not ask for it as a routine question.

## Workflow (remind + propose)

```
Bugfix regression:
- [ ] 1. Identify the failure (symptom, wrong value, trigger inputs)
- [ ] 2. Decide: new regression file vs extend an existing test module
- [ ] 3. Write the test; show it red on the unfixed code (or an xfail(strict=True) that turns into XPASS with the fix)
- [ ] 4. Fix; run the focused pytest green, then the suite
- [ ] 5. Commit fix + test together; Verifications Pending names the test path
```

### Step details

1. **Reproduce in the test.** Use the smallest inputs that failed (a tariff JSON fragment, a few slots, one date). For tariff bugs the typical fixtures are: a rule window across midnight, a holiday, a DST change day (last Sunday in March/October), a missing market price, a 60-minute settlement tariff.
2. **Where to put it.** Prefer `tests/test_<topic>_regression.py` for cross-module or fixture-driven cases; extend a focused `tests/test_*.py` only when the bug is local. Name the test after the bug, not the fix.
3. **Reference.** In the docstring cite the GitHub issue (`https://github.com/JochenTCC/Edibert/issues/N`) or a one-line symptom.
4. **Write it, do not ask first.** The test is part of the fix. Say in chat which file, which failure mode and which assertions it locks in. When a bug is found but its fix is not wanted yet, commit the test as `xfail(strict=True)` with the reason, so it fails loudly once the fix lands.
5. **Run:**

   ```powershell
   $env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -m pytest tests/test_<file>.py -q --tb=short
   ```

## Fixture rules

- Use **placeholder or anonymized** data only. Never commit customer data, real invoices, meter numbers, or postal codes (see `edibert-project.mdc`).
- Real published examples (a grid operator's price table) are marked unverified in the fixture.

## Quality bar

- The test fails on the **pre-fix** behavior (conceptually) and passes after.
- No mock-only tests that never exercise the buggy path.
- Deterministic; no live network.
- Do not generate large datasets without asking.
