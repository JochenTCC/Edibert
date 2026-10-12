---
name: bugfix-regression-test
description: >-
  After each code bugfix, remind to add a regression test and propose a concrete
  test (prefer a dedicated regression file; cite the GitHub issue when
  available). Use when implementing a bugfix, fixing a GitHub issue, or when a
  wrong tariff price, rule match, holiday handling, or price series is found.
---

# Bugfix regression test

Soft gate: for every **code** bugfix, remind and **propose** an appropriate regression test so the same failure cannot silently return. Do **not** block the fix if the user declines; record the skip reason briefly.

## Exceptions (no new test required)

State the exception once; do not invent a worthless test.

| Exception | Action |
|-----------|--------|
| Docs-only change | skip |
| Pure config / environment mistake with **no** wrong code path | note in reply; skip |
| User explicitly declines a regression test | note decline; continue |

## Workflow (remind + propose)

```
Bugfix regression:
- [ ] 1. Identify the failure (symptom, wrong value, trigger inputs)
- [ ] 2. Decide: new regression file vs extend an existing test module
- [ ] 3. Propose the test to the user (name, assertion, fixture/inputs)
- [ ] 4. If accepted: implement, run focused pytest
- [ ] 5. If declined / exception: one-line reason in chat
```

### Step details

1. **Reproduce in the test.** Use the smallest inputs that failed (a tariff JSON fragment, a few slots, one date). For tariff bugs the typical fixtures are: a rule window across midnight, a holiday, a DST change day (last Sunday in March/October), a missing market price, a 60-minute settlement tariff.
2. **Where to put it.** Prefer `tests/test_<topic>_regression.py` for cross-module or fixture-driven cases; extend a focused `tests/test_*.py` only when the bug is local. Name the test after the bug, not the fix.
3. **Reference.** In the docstring cite the GitHub issue (`https://github.com/JochenTCC/edbert/issues/N`) or a one-line symptom.
4. **Propose before writing (default).** In chat: target file, failure mode, key assertions, fixture source. Implement after acceptance, or if the user asked for fix **and** test in the same turn.
5. **Run:**

   ```powershell
   $env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -m pytest tests/test_<file>.py -q --tb=short
   ```

## Fixture rules

- Use **placeholder or anonymized** data only. Never commit customer data, real invoices, meter numbers, or postal codes (see `edbert-project.mdc`).
- Real published examples (a grid operator's price table) are marked unverified in the fixture.

## Quality bar

- The test fails on the **pre-fix** behavior (conceptually) and passes after.
- No mock-only tests that never exercise the buggy path.
- Deterministic; no live network.
- Do not generate large datasets without asking.
