# Tariff catalog

This directory is **reserved** for the tariff catalog. No catalog is stored here.

Planned structure:

- The catalog is shipped as a **signed package** with a validity date, verifiable offline and importable manually.
- Each tariff carries: country, grid area, supplier, product, rules and prices, `source` (URL or document name), `last_verified` and the `verified` flag.
- Access is available to users with an accepted contribution (time-limited) or with a one-time fee (time-limited). The terms are published after legal review, per country in the national language.
- **Decided (2026-10-28, Earnie *Edibert P8*):** the public Earnie catalog (`share/config/tariffs.json`, `share/config/grid_fees.json`) is a frozen seed. It gets corrections and its monthly reference curves, but no new entries; new tariffs and grid areas reach users only through this channel.

Open before anything is published here:

- Legal review of the terms of use, of data protection for the upload, and of payment handling.
- Signing and key management.
