# Publishing and market data (0.1.e)

Technical description. Users read [docs/user/en/publishing.md](../user/en/publishing.md).

## Layers

```
sources.py   HTTP + parsers          -> {slot_start_utc: cent/kWh}   (ENTSO-E, Energy-Charts, aWATTar)
cache.py     market_<zone>.json      -> CacheEntry
service.py   MarketService.load()    -> MarketData (chain, freshness, partial answers)
forecast.py  mirror / hold (library); plug-ins: publish/forecasters.py -> Forecaster.forecast(known, start, end)
publish/     config, payloads, mqtt, service, command
```

All HTTP goes through an injectable `HttpGet(url, params, timeout) -> str`; tests use fakes. Nothing in the library reads the clock without a parameter: `MarketService.load(tz, now)` and `Publisher.run_cycle(now)` take the time.

## Market chain

Same order as Earnie: cache -> ENTSO-E A44 (only with `ENTSOE_API_TOKEN`) -> Energy-Charts -> aWATTar (AT and DE-LU only).

* Zone by country: AT -> `AT`, DE -> `DE-LU`, CH -> `CH` (`MARKET_ZONE_UNKNOWN` otherwise).
* Units: EUR/MWh from the sources, stored as cent/kWh (divide by 10). Hourly data is expanded to four 15-minute slots. A finer resolution wins over a coarser one in the same ENTSO-E document.
* ENTSO-E curve type A03 omits a point when the price equals the previous one; the parser carries the last price forward inside a period. Energy-Charts `null` values are skipped, they are not zero.
* Expected window: from local midnight today to local midnight after the last Day-Ahead day. The last Day-Ahead day is tomorrow from 12:00 local on (`DAY_AHEAD_PUBLISH_HOUR`, Earnie uses the same constant), else today. The window is counted in UTC slots, so DST days have 92 or 100 slots.
* A result is **complete** if every slot of the window is present. Freshness is decided by coverage, not by the download time: a cache from the morning is not complete after 12:00 because tomorrow is missing.
* If the cache is incomplete but was checked less than 10 minutes ago, the sources are not asked again (`RETRY_MINUTES`).
* The first source with a complete answer wins and is written to the cache (slots before today are dropped). If none is complete, the partial answer with the most slots is used (cache included) and `MARKET_DATA_INCOMPLETE` is reported; without any answer: `MARKET_DATA_UNAVAILABLE`.
* A failed source is a `MARKET_SOURCE_FAILED` warning. Tokens are removed from the message (`redact`).
* A damaged cache file is a `MARKET_CACHE_UNREADABLE` warning; it is rebuilt.

Deviation from Earnie: Earnie places a stale cache before aWATTar by time; Edbert picks the best partial answer by slot coverage.

## Publisher

`Publisher.run_cycle(now)`:

1. Market data is loaded only if some configured tariff `uses_market_price`.
2. Per tariff, `tariff_price_series` is evaluated from local midnight today to the end of tomorrow. For market tariffs the end is the end of today if tomorrow is not fully covered (`tomorrow_valid: false`). If today is not covered the tariff goes offline: availability `offline`, no state, error reported (`MARKET_DATA_UNAVAILABLE`). Other tariffs are not affected.
3. The grid fee of `house.json` is applied to import tariffs only.
4. `forecast` (optional): the forecaster is called for `[end of exact series, + hours)`; its market prices are merged over the known ones and the tariff is evaluated with `forecast_from`. Forecast points are published only in `forecast`. A failing plug-in gives `FORECAST_FAILED`; exact prices stay.

`run_forever` runs a cycle at start and then at every quarter-hour boundary (+2 s). On exit the bridge status is set to `offline`; the MQTT last will does the same if the process dies.

## Topics and payloads

* State: price of the current interval in EUR/kWh, rounded to 5 decimals (cent / 100). Empty if no interval matches.
* `raw_today`, `raw_tomorrow`, `forecast`: lists of `{start, end, value}`; `start`/`end` ISO 8601 with the house offset.
* Discovery: one `sensor` per tariff, `unit_of_measurement: EUR/kWh`, `availability_mode: all` over the bridge status and the tariff availability, one device "Edbert". No `device_class` (Home Assistant's `monetary` class does not allow a per-kWh unit).
* All messages are retained, QoS 1. Credentials come from environment variables named in `publish.json`; the file never holds a secret.
* Removing a tariff from `publish.json` does not delete its retained topics.

## Forecast

`forecast.method` in `publish.json`: `mirror` (default), `hold` or `plugin`. A forecaster implements `forecast(known, start, end) -> {slot_start_utc: cent/kWh}` where `known` are the real market prices (including the cached history).

* `MirrorForecaster(tz)`: same **local** time of day on the nearest earlier day within 7 days that has a real price (`MAX_MIRROR_LOOKBACK_DAYS`, as in Earnie's `find_mirror_slot`); DST-safe through wall-clock arithmetic. Slots without a source are left out.
* `HoldLastForecaster`: the last real price before `start`, constant.
* `plugin` (product layer, `edbert.publish.forecasters`): entry-point group `edbert.forecasters`; the entry point is a class or factory called as `factory(key=...)`. The key comes from `EDBERT_FORECAST_KEY`; Edbert requires it (`FORECAST_KEY_MISSING`), validating it is the plug-in's job, so the free edition contains no validation. How keys are issued and checked is not decided yet. Earnie's regression model can be wrapped as such a plug-in.
* The publisher starts the forecast where the exact series ends, asks for `hours` (1 to 72, `MAX_FORECAST_HOURS`, default 48), and cuts the result at the last gap-free **whole hour** (`_covered_end`). A forecaster that returns nothing yields an empty `forecast`; an exception yields `FORECAST_FAILED` and exact prices stay.
* The market cache keeps 7 days of history (`HISTORY_DAYS`) and merges new downloads into it; history is not downloaded, it accumulates while Edbert runs.
* Attribute `forecast_method` names the method (or the plug-in name) when a forecast is present.

## Open points

* Cleanup of retained topics of removed tariffs.
* Home Assistant action `get_rates(start, end, resolution)` (needs the native integration).
