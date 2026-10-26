# Architecture

Decision of 2026-10-12. Edibert is delivered in layers; the same code serves the free product and Earnie.

| Layer | Content | Used by |
|---|---|---|
| Shared library (later) | Cached access to external data, first of all weather | Edibert plug-ins, Earnie |
| **Edibert library** | Tariff editing (form model, checks), persistence, rule engine, grid fee, market-price chain, price series for the future **and** the past, forecaster interface | Edibert product, Earnie |
| **Edibert product** | MQTT output (more targets later), editor page, loading of plug-ins with a key; delivers future data only | End users without Earnie |

## Rules

1. The library knows neither the UI nor MQTT. A test checks that `edibert.ui` and `edibert.publish` are not imported by the library modules. Earnie uses the library through the direct API `edibert.api` ([api.md](api.md)); the layering is checked by `tests/test_api.py`.
2. Only Edibert supplies tariff data.
3. **Market prices belong to the library**, because they are the input of the tariff calculation. Consumers such as Earnie read them there, also for non-tariff purposes. The chain exists once. Price queries for arbitrary ranges (simulation/backtesting) come from `market/archive.py` with a per-month long-range cache (since `0.1.g`).
4. **Past and future:** the library prices past periods too. For missing monthly rates the Earnie rule applies: exact month, else the same month of the previous year, else the previous month, always reported as a coded warning (`MONTH_RATE_FALLBACK`, since `0.1.g`). This also applies when the 72-hour window reaches a month change. If no entry exists, it is an error.
5. **Forecast:** at most 72 hours. Methods: `mirror`, `hold`, plug-in. A forecaster *object* can be handed to the library directly (Earnie does this with its OLS model, no key). The key (`EDIBERT_FORECAST_KEY`) belongs to the product layer and guards only plug-ins loaded through the entry-point group. The library (`market/forecast.py`) holds the interface and the free methods (`builtin_forecaster`); plug-in loading and the key live in the product (`publish/forecasters.py`).
6. Weather is not tariff data. It goes into a shared library that is built when the forecast plug-in needs it. Location: open (proposal: standalone package without Earnie imports first, own repository later).

## Consequences for the price series

* Every point also carries the market price of the slot (`market_cent`) and the method behind the quality (`exact`, `mirror`, `hold`, plug-in name), since `0.1.g`.
* Tariffs that change over time (new prices from a date) are not modelled yet.

## Open points

License when Earnie contains the library, packaging (PyPI, pinned git tag, vendored copy; Docker image, Home Assistant add-on), and how the simulation deals with old and new tariff formats.
