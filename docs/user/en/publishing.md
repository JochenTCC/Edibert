# Publishing prices over MQTT

Edibert can send the prices of your tariffs to an MQTT broker. Home Assistant finds the sensors by itself (MQTT discovery); other systems read the topics directly.

```bash
pip install -e ".[mqtt]"
python -m edibert publish --data-dir edibert_data
```

The command runs until you stop it with Ctrl+C. It publishes at start and again at every quarter hour, so the current price is always up to date. `--once` publishes one time and exits, `--dry-run` prints the topics instead of sending them (no broker needed).

## What you need in the data folder

The folder is the one you use for the editor (`--data-dir`):

| File | Content |
|---|---|
| `user_tariffs.json` | your tariffs, written by the editor |
| `house.json` | time zone, country, region and grid fee, written by the editor |
| `publish.json` | which tariffs to publish and where (you write this file once) |

```json
{
  "mqtt": {
    "host": "192.168.1.20",
    "port": 1883,
    "username_env": "EDIBERT_MQTT_USER",
    "password_env": "EDIBERT_MQTT_PASSWORD",
    "tls": false,
    "base_topic": "edibert",
    "discovery_prefix": "homeassistant"
  },
  "tariffs": [
    { "id": "user_my_spot" },
    { "id": "user_my_feed_in", "direction": "export" }
  ],
  "resolution_min": 15
}
```

* `username_env` and `password_env` are the **names of environment variables**. The user name and the password are never stored in a file.
* `direction` is `import` (default) or `export` (feed-in).
* `resolution_min` is 15, 30 or 60 minutes.
* Only `host` is required in `mqtt`.

## Market prices

Tariffs that depend on the market price (spot tariffs, or rules with a market-price condition) need the Day-Ahead prices. Edibert gets them the same way Earnie does:

1. the local cache (`market_<zone>.json` in the data folder),
2. ENTSO-E Transparency, if the environment variable `ENTSOE_API_TOKEN` is set (a free token from entsoe.eu),
3. Energy-Charts (free, no token),
4. aWATTar (Austria and Germany only).

The Day-Ahead prices for tomorrow appear around 12:00 CET. From then on Edibert expects them; until they are there, only today is published and `tomorrow_valid` is `false`. If a source fails, the next one is tried. If no source has all prices, the best partial answer is published and the gap is reported; if today's prices are missing, the market tariffs go **offline** (no price is invented). Tariffs without a market price (fixed, time windows) are never affected.

Data from Energy-Charts.info (Fraunhofer ISE) is licensed under CC BY 4.0; Edibert names the source in the sensor attributes.

## Topics

For a tariff `<id>` with direction `<dir>` (`import` or `export`):

| Topic | Content |
|---|---|
| `edibert/<dir>/<id>/state` | current price in EUR/kWh (retained) |
| `edibert/<dir>/<id>/attributes` | JSON, see below (retained) |
| `edibert/<dir>/<id>/availability` | `online` or `offline` (retained) |
| `edibert/status` | `online` while Edibert runs, `offline` when it stops or the connection is lost |
| `homeassistant/sensor/edibert_<dir>_<id>/config` | Home Assistant discovery |

Attributes (excerpt): `current_cent_kwh`, `components` (supplier, grid, vat in EUR/kWh), `next`, `average_today`, `min_today`, `max_today`, `raw_today` and `raw_tomorrow` (lists of `{start, end, value}` in EUR/kWh, the format known from Nordpool and evcc), `tomorrow_valid`, `forecast`, `market` (zone, source, time of download, attribution) and `updated`.

## Forecast (optional)

The Day-Ahead prices end with the next day. If you want prices further ahead (for example to plan a battery or a heat pump over several days), add a `forecast` section to `publish.json`. Forecast prices are run through your tariff like real prices, but they are published only in the attribute `forecast` (with `forecast_method`), never in `raw_today` or `raw_tomorrow`.

```json
"forecast": { "method": "mirror", "hours": 48 }
```

| `method` | What it does | Needs |
|---|---|---|
| `mirror` (default) | takes the price of the same time of day from an earlier day, up to 7 days back (as in Earnie) | nothing |
| `hold` | keeps the last known price constant | nothing |
| `plugin` | a forecast model from an installed package, with `"name": "my_forecaster"` | the package and a **key** in the environment variable `EDIBERT_FORECAST_KEY` |

`hours` is how far the forecast reaches (1 to 72, default 48). The forecast ends where no price can be derived, at a whole hour. For `mirror`, Edibert keeps the last 7 days of prices in the cache, so it needs about a day of running time before it can look back that far.

The free edition of Edibert contains no plug-in; the key unlocks it. If the plug-in or the key is missing, Edibert stops with an error and tells you to set the key or to choose `mirror` or `hold`. If a plug-in fails while running, only the exact prices are published and a warning is shown.
