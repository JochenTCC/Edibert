# Contributing to Edibert

Edibert is still in draft. This document describes how contributions will work later. The terms for contributions and the catalog, and the privacy notice, are published after legal review; **until then no tariffs are accepted**. The code is licensed under [PolyForm Noncommercial 1.0.0](LICENSE).

## Contributing tariffs

The catalog lives on tariffs that users have recorded. You can contribute a tariff if it

- is **not tailored to you** (no special conditions, no customer code),
- has a **public price sheet** you can point to,
- passed the **invoice check** against a real invoice in the editor, or you can cite the price sheet.

### What is transmitted

| Transmitted | Never transmitted |
|---|---|
| Country, grid area | Postal code, address, name |
| Supplier, product name | Meter number, contract number |
| Rules and prices | Consumption data |
| Source (URL or document name), verification date | Free text (notes) |
| Result of the invoice check (passed yes/no) | Invoice files or photos |

Before sending, Edibert shows the **exact content**. Nothing is sent without your explicit confirmation per tariff. Tariffs you mark as `individual` are never transmitted.

### What happens afterwards

1. Check for duplicates and plausibility.
2. Acceptance only after a passed invoice check or confirmation by a second user (`verified`).
3. Accepted contributions give you time-limited access to the catalog and its updates.

Which terms apply: contributions through Edibert fall under Edibert's own contribution terms (see the README, section License; published after legal review). Contributions made from within Earnie are, until then, covered by the draft in Earnie's [`LICENSE.md`](https://github.com/JochenTCC/Earnie/blob/main/LICENSE.md) § 3 paragraphs 4–8; once Edibert's terms are published they take precedence there too.

Until the upload function exists, the route is a GitHub issue using the "tariff contribution" template (to follow).

## Contributing code

Not possible yet: the format is a draft. Questions and comments about the format are welcome as issues. Contributions are licensed under this repository's license ([LICENSE](LICENSE)). Open question: whether code contributions need consent to relicensing so that a commercial license remains possible.

## Conventions

- **Language:** all technical documents are English only (specification, backlog, rules, code, comments, commit messages, issues, this file). The English README is authoritative; `README.de.md` is a translation. User manuals exist in English (authoritative) and German. See `.cursor/rules/docs-language.mdc`.
- **UI texts** go through the translation catalogs (`src/edibert/i18n/catalogs/`); never hard-code visible strings.
- **Legal texts** are written per country in the national language (DE/AT: German, CH: German) and are not kept in this repository until legally reviewed.
- No real names, addresses or customer data in examples, tests or issues.
