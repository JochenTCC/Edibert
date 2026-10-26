# Edibert

**English** · [Deutsch](README.de.md) · *The English version is authoritative.*

*Formerly named Edbert (renamed 2026-10-26).*

**Edibert** is a tariff editor and price service for smart-home systems. You describe your electricity tariff once (fixed, market-indexed, or time-variable with windows, weekdays and holidays) and Edibert delivers the resulting prices as a time series to your smart-home backend: as a Home Assistant sensor or over MQTT.

> **Status: draft.** The rule engine (`0.1.a`), the price series with grid fee (`0.1.b`) the tariff editor in the browser (`0.1.c`) and the MQTT publisher with Home Assistant discovery (`0.1.e`) work. A native Home Assistant integration does not exist yet. See the [roadmap](#roadmap).

## The tariff editor

```bash
pip install -e ".[ui]"
python -m edibert ui --data-dir edibert_data
```

Open `http://localhost:8501`. Four steps (base price, time windows, further costs, advanced), live price curve, price at a given time, check against a real invoice, copy a catalog tariff, import JSON. English and German. See the [user manual](docs/user/en/index.md).

## Publish over MQTT

```bash
pip install -e ".[mqtt]"
python -m edibert publish --data-dir edibert_data
```

Sends the prices of the tariffs listed in `publish.json` (current price, today, tomorrow, optional forecast) as retained MQTT topics with Home Assistant discovery. Market prices come from the same chain as in Earnie (ENTSO-E with a token, Energy-Charts, aWATTar). See [Publishing](docs/user/en/publishing.md).

## Try it

```bash
pip install -e ".[dev]"
python -m edibert price --tariff examples/spot_evening_surcharge_cap.json     --at 2026-12-15T18:00 --tz Europe/Vienna --epex 10
python -m edibert --lang de price --tariff examples/fixed_day_night.json     --at 2026-12-25T12:00 --tz Europe/Berlin --land DE --region BY
python -m pytest
```

The first command prints the price of one slot with the steps (base price, applied rule, floor/cap, VAT). Tariffs with weekday rules need `--land` and `--region`, because holidays can change the result; without them the command stops with an error instead of guessing. `python -m edibert schema` prints the JSON Schema of a tariff.

```bash
python -m edibert series --tariff examples/spot_evening_surcharge_cap.json \
    --grid-fee examples/grid_fee_modul3_example.json \
    --from 2026-12-15T00:00 --to 2026-12-16T00:00 --tz Europe/Vienna \
    --market-csv tests/fixtures/market_2026-12-15.csv --resolution 60
```

`series` prints prices over a time range (15, 30 or 60 minutes) from day-ahead prices in a CSV (`timestamp,cent_kwh` per quarter hour), optionally with a grid fee. Missing market prices stop the command with an error. Warnings go to stderr.

## Why?

Many tariffs cannot be described by a single "ct/kWh" field:

- night tariffs and weekend prices (peak/off-peak), summer midday windows
- market price with markups, price cap and floor
- time-variable grid fees (§14a EnWG module 3: high, standard and low tariff)
- feed-in with "no remuneration at negative prices"
- public holidays that count like a Sunday

Edibert models this with a few building blocks, **without hand-written JSON**, and shows you the price curve immediately, before you use it.

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

Non-goals: comparing or brokering tariffs, creating invoices, controlling devices. Edibert only delivers prices.

## Relation to Earnie

Edibert is a stand-alone tool that is also used by [Earnie](https://github.com/JochenTCC/Earnie), an optimizer for home batteries, PV and loads. You do not need Earnie to use Edibert.

## Catalog and contributions

Edibert has a curated catalog of tariffs (DE/AT/CH). You can always create your own tariffs. Access to the **community catalog and its updates** is available to users

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
| T3b | MQTT publisher, market price chain, forecast (mirror, hold, key-gated plug-in) |
| T4 | Contribution path and signed catalog access |
| later | Price-sheet assistant, output for evcc/EMHASS/Predbat, prices per meter |

The format is described in [docs/spec/tariff-format.md](docs/spec/tariff-format.md) and [docs/spec/publishing.md](docs/spec/publishing.md); examples are in [examples/](examples/). User manuals: [docs/user/en/](docs/user/en/).
