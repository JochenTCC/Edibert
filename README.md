# Edbert

**English** · [Deutsch](README.de.md) · *The English version is authoritative.*

**Edbert** is a tariff editor and price service for smart-home systems. You describe your electricity tariff once (fixed, market-indexed, or time-variable with windows, weekdays and holidays) and Edbert delivers the resulting prices as a time series to your smart-home backend: as a Home Assistant sensor or over MQTT.

> **Status: draft.** This repository currently contains the concept, the format description and examples. There is no runnable engine yet. See the [roadmap](#roadmap).

## Why?

Many tariffs cannot be described by a single "ct/kWh" field:

- night tariffs and weekend prices (peak/off-peak), summer midday windows
- market price with markups, price cap and floor
- time-variable grid fees (§14a EnWG module 3: high, standard and low tariff)
- feed-in with "no remuneration at negative prices"
- public holidays that count like a Sunday

Edbert models this with a few building blocks, **without hand-written JSON**, and shows you the price curve immediately, before you use it.

## Planned features

| Feature | Description |
|---|---|
| Tariff editor | Guided form in four steps, price curve preview, warning for rules that never apply, invoice check against a real invoice |
| Multilingual | UI and user manual in German and English |
| Rule engine | Base price + time rules (months, weekdays, time of day, holidays), floor/cap, VAT, grid fee |
| Price series | Calculated prices for a selectable horizon (15, 30 or 60 minutes), for import **and** feed-in |
| Output | Home Assistant sensors (`raw_today`, `raw_tomorrow`, `forecast`) and MQTT (retained, with HA discovery) |
| Import | Catalog tariff as template, JSON file, price series (CSV), later a price-sheet assistant |
| Holidays | From the [`holidays`](https://github.com/vacanza/holidays) library (DE/AT/CH by federal state or canton), offline |

Non-goals: comparing or brokering tariffs, creating invoices, controlling devices. Edbert only delivers prices.

## Relation to Earnie

Edbert is a stand-alone tool that is also used by [Earnie](https://github.com/JochenTCC/Earnie), an optimizer for home batteries, PV and loads. You do not need Earnie to use Edbert.

## Catalog and contributions

Edbert has a curated catalog of tariffs (DE/AT/CH). You can always create your own tariffs. Access to the **community catalog and its updates** is available to users

- who have contributed a tariff themselves (for a limited time), or
- who pay a small one-time fee.

A yearly subscription for automatic catalog updates is planned for later. The software itself always works, also without catalog access.

Only tariffs that are **not tailored to one person** are collected, and only **without personal data** (no postal code, name, meter number, free text or consumption data). Upload is voluntary, with a preview of the exact content. This describes the planned behavior, not a binding offer. Details: [CONTRIBUTING.md](CONTRIBUTING.md) and [catalog/README.md](catalog/README.md).

## License

The code is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE): source available; use for private, scientific, charitable and other **non-commercial** purposes is allowed; commercial use requires a separate license. This is not an open-source license in the OSI sense ("source-available").

[LICENSE](LICENSE) and [NOTICE](NOTICE) apply to the code. The tariff catalog and tariff contributions are covered by **separate terms** and a privacy notice. These legal texts are written **per country in the national language** (Germany and Austria: German; Switzerland: German) and are published here **only after legal review**; until then there is neither catalog access nor upload.

## Roadmap

| Step | Content |
|---|---|
| T1 | Rule engine, tariff fields, `user_tariffs.json`, holidays, multilingual foundation |
| T2 | Grid-fee rules and `tariff_price_series` (the single interface to the price series) |
| T3 | Editor and import (template, JSON file) |
| T4 | Contribution path and signed catalog access |
| later | Price-sheet assistant, output for evcc/EMHASS/Predbat, prices per meter |

The format is described in [docs/spec/tariff-format.md](docs/spec/tariff-format.md); examples are in [examples/](examples/). User manuals: [docs/user/en/](docs/user/en/).
