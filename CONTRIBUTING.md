# Contributing to Edibert

Edibert is still in draft. This document describes how contributions will work later. The terms for sharing tariffs and for the catalog, and the privacy notice, are published after legal review; **until then no tariffs are accepted**. The code is licensed under [PolyForm Noncommercial 1.0.0](LICENSE).

## Sharing tariffs

Tariffs reach the **free database** only through the share section of the editor; there is no route through GitHub issues. A shared tariff is unchecked at first and earns the status `reliable` by use: a tariff version used by at least two installations within 12 months (you count as one). The **verified database** is kept separately by us and is not filled by shared tariffs directly. Sharing earns no catalog access and no reward; it helps others with the same tariff.

Share a tariff only if it is **not tailored to you** (no special conditions, no customer code). Tariffs you mark as `individual` are never shared, and a tariff without a country cannot be shared.

### What is transmitted

Edibert builds the content from a fixed list of fields; everything else is left out.

| Transmitted | Never transmitted |
|---|---|
| Country, regions, grid area | Postal code, address, name |
| Supplier, product name | Meter number, contract number |
| Rules, prices, fees, VAT, monthly rates | Consumption data |
| Source (URL or document name), verification date, validity | Free text (notes, comments) |
| | An installation ID |

Before sending, the share section shows the **exact content** of every selected tariff, and every tariff can be left out. Whether tariffs are selected by default is set by the program that embeds the editor: the stand-alone editor selects them, Earnie only after you opted in.

### What happens afterwards

1. The server checks the tariff and answers with its database ID: accepted, already known (duplicate), or rejected with a reason the editor shows.
2. A changed version of a tariff you shared before becomes a new version of the same entry.
3. Accepted tariffs reach other users with the next free catalog package; use reports of installations decide when a version counts as `reliable`.

Which terms apply: tariffs shared through Edibert fall under Edibert's own terms (see the README, section License; published after legal review). Tariffs shared from within Earnie are, until then, covered by the draft in Earnie's [`LICENSE.md`](https://github.com/JochenTCC/Earnie/blob/main/LICENSE.md) § 3 paragraphs 4–8; once Edibert's terms are published they take precedence there too.

## Contributing code

Not possible yet: the format is a draft. Questions and comments about the format are welcome as issues. Code contributions will need a contributor license agreement (CLA): you keep your copyright and grant a simple, perpetual right of use that includes the right to sublicense, so that commercial licenses remain possible. You sign it in the pull request. The text follows after legal review; until then no code contributions are accepted.

## Conventions

- **Language:** all technical documents are English only (specification, backlog, rules, code, comments, commit messages, issues, this file). The English README is authoritative; `README.de.md` is a translation. User manuals exist in English (authoritative) and German. See `.cursor/rules/docs-language.mdc`.
- **UI texts** go through the translation catalogs (`src/edibert/i18n/catalogs/`); never hard-code visible strings.
- **Legal texts** are written per country in the national language (DE/AT: German, CH: German) and are not kept in this repository until legally reviewed.
- No real names, addresses or customer data in examples, tests or issues.
