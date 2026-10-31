# Tariff catalog

This directory is **reserved** for the tariff catalog. No catalog is stored here.

Planned structure:

- **One tariff database** (decided 2026-10-31; before: a free and a verified database), free, without a key, one ID space (`<LAND>/<import|export|grid>/<id>`). Every version carries a **check state** (`unchecked`, `checked` with date and source, `released_by_supplier` with date and releasing party, `rejected`), the use status `reliable` (at least two installations within 12 months, the one who shared it counts) and a lifecycle (current, superseded, blocked, merged into another ID). The trust level shown to users is derived: released by supplier > checked > reliable > unchecked.
- Two views: the **catalog** holds the current checked and supplier-released versions as a **signed catalog package** with a validity date, verified offline and importable manually or loaded from the server (`python -m edibert exchange fetch`, then `package import`; see the [CLI manual](../docs/user/en/cli.md)). All other admitted versions are **templates** (`python -m edibert exchange templates`, or the editor after an opt-in), only ever copied into the user's own tariffs. Contract: [catalog-exchange.md](../docs/spec/catalog-exchange.md). Contributions earn no access; there is no GitHub-issue route.
- Each catalog tariff carries: country, grid area, supplier, product, rules and prices, `source` (URL or document name), `last_verified`, and in a package its `check` (state, date, source or releasing party).
- The terms are published after legal review, per country in the national language.
- **Decided (2026-10-28, Earnie *Edibert P8*):** the public Earnie catalog (`share/config/tariffs.json`, `share/config/grid_fees.json`) is a frozen seed. It gets corrections and its monthly reference curves, but no new entries; new tariffs and grid areas reach users only through this channel.

Open before anything is published here:

- Legal review of the terms of use, of data protection for sharing, and of the data license.
