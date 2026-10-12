---
name: doc-review-findings
description: >-
  Correct open items under ## Document Review Findings in
  backlog/Backlog-Bugfixes.md (README, user docs, spec links, renames,
  TOC), then archive them in backlog/Backlog-Erledigt.md. Use when the user
  asks to fix document review findings or clear that chapter.
---

# Document review findings

Source chapter: `## Document Review Findings` in `backlog/Backlog-Bugfixes.md`.

Unlike code bugfixes these items **skip** `## Bugfix Verifications Pending`: after the doc change is done, move straight to `backlog/Backlog-Erledigt.md`.

## When this skill applies

- The user points at `## Document Review Findings` or asks to process those items.
- You are about to edit docs solely to clear a finding from that chapter.

## Workflow

```
Doc review finding:
- [ ] 1. Read the finding (and nested bullets) fully; ask if scope is unclear
- [ ] 2. Locate target docs / links
- [ ] 3. Apply the correction (English first, then the German counterpart — docs-language.mdc)
- [ ] 4. Update cross-links (README, docs/spec/tariff-format.md references)
- [ ] 5. Remove the finding from Backlog-Bugfixes.md (keep the empty chapter heading)
- [ ] 6. Archive in Backlog-Erledigt.md as ### Document Review … (YYYY-MM-DD) with - [x]
```

### Step details

1. **Scope:** one finding (top-level `- [ ]`) per pass unless the user asks for a batch. Ask before inventing content the finding does not specify.
2. **Language:** technical docs English only; user pages English (authoritative) and German (`README.md`/`README.de.md`, `docs/user/en|de/`). See `docs-language.mdc`.
3. **Legal texts:** never paraphrase or add binding legal texts to this repo (`edbert-project.mdc`).
4. **Archive:** use the heading format `### Document Review <topic> (YYYY-MM-DD)`, newest on top, date in Europe/Vienna.

## Do not

- Route doc findings through `## Bugfix Verifications Pending`
- Change code behavior while fixing docs
- Edit `LICENSE`
