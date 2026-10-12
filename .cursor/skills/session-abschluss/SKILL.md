---
name: session-abschluss
description: >-
  End-of-session routine for Edbert: backlog sync, commit approved changes,
  push, and the publish decision. Use when the user wants to end the session,
  sync the backlog, commit and push, or tag a release. Lean version of the
  Earnie skill (no Docker, no promote job).
---

# Session conclusion (Edbert)

Commit and push approval is implied by the end-session request. Still: never commit secrets, gitignored files, real tariff or customer data, or the draft legal texts.

## Phase 1 — backlog, commit, push

```
Session conclusion:
- [ ] 1. Backlog sync (Backlog.md / Backlog-Bugfixes.md / Backlog-Erledigt.md) per backlog.mdc
- [ ] 2. Bugfix in this session? → regression test proposed/added (bugfix-regression-test)
- [ ] 3. Anonymize user names in Backlog-Bugfixes.md / Backlog-Erledigt.md (backlog-anonymize-users.mdc)
- [ ] 4. Tests green: PYTHONPATH=src python -m pytest -q (UTF-8 env, windows-unicode-console)
- [ ] 5. Ask about local or possibly temporary files before staging
- [ ] 6. Version unchanged unless the user approved a bump (versioning.mdc)
- [ ] 7. Commit (English message, roadmap syntax) and push
```

Details:

1. **Backlog:** move finished items to `backlog/Backlog-Erledigt.md` (`### <topic> (YYYY-MM-DD)`, newest on top, `- [x]`). Fix-implemented bugs go to `## Bugfix Verifications Pending`, not to the archive.
2. **Do not stage:** `user_tariffs.json`, `.env`, `secrets/`, `coverage.xml`, `.cursor/user-aliases.local.md`, anything outside the repo.
3. **Legal drafts:** if the session touched legal texts, check that they remain in the Earnie project folder and were not added to this repo.
4. **Spec consistency:** if the tariff format changed, spec (`docs/spec/tariff-format.md`), README feature table, examples, and the Earnie development document must agree; mention any that were left out of sync.
5. **Commit message:** `<scope>: <version> <phase/step> <description>`, e.g. `engine: 0.1.a P1 rule matcher with wrap-around windows` (`roadmap-nomenclature.mdc`).

## Publish decision (only after Phase 1)

Present once, with the live package version and one recommended choice:

| Choice | Meaning |
|---|---|
| **A** | skip, nothing to publish |
| **B** | pre-release (needs approved version bump to `…a1/b1/rc1`) |
| **C** | official release (needs approved version bump) |

## Phase 2 — tag (only on request)

1. Version bump only after explicit approval; `pyproject.toml` and `src/edbert/__init__.py` must match.
2. Annotated tag `vX.Y.Z[…]` matching the package version. Never rewrite or force-push a published tag; fix forward with a new approved version.
3. Publishing to PyPI / HACS is **not** automated by this skill; it needs a separate decision (license note: PolyForm Noncommercial; HACS requirements in the backlog research items).

## Do not

- Bump the version without approval
- Tag or publish automatically
- Push before the user has seen what is staged when private or unclear files are involved
