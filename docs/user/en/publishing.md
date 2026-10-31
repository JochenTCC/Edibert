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

## Tariff database (optional)

The publisher can talk to the tariff database server (see [CLI](cli.md), section exchange): report which catalog tariffs you use, ask whether there is a newer version, and keep your catalog up to date. Nothing is sent unless you add this block to `publish.json`:

```json
"exchange": { "report_use": true, "status": true, "packages": true }
```

| Job | What it does |
|---|---|
| `report_use` | once a day, per tariff that comes from the database, one message at a random time with its database ID, version and a pseudonym computed on your computer (no installation ID, the pseudonym differs for every tariff) |
| `status` | once a day asks for the check state and the newest version of these tariffs and whether they count as reliable |
| `packages` | once a week (or before the current package expires) loads the catalog package and imports it; needs `--catalog` |

All three must be named, `true` or `false`. `EDIBERT_EXCHANGE_OFF=1` switches everything off. The catalog package of the tariff database is free, needs no key and holds only checked tariffs and tariffs released by their supplier.

A package is imported automatically only when nothing is lost: if it would change monthly rates you entered yourself, or if it no longer contains a tariff you publish, it is not imported and a warning says why. Import it then in the editor (sidebar, *Import catalog package*) and decide there. A failure of the server never touches the prices; the job is tried again an hour later.

Each tariff's attributes get a block `catalog` with its database ID and version, its check state and date (`check_state`, `checked_at`), `reliable`, the `trust_level` (`released_by_supplier`, `checked`, `reliable`, `unchecked`) and `check_overdue` (the last check is older than a quarter plus 30 days). A catalog tariff from an imported package shows its check state even without `status`. With `status` the block also says how many installations used it in the last 12 months, whether a newer version exists (`newer_version`, `newer_valid_from`), whether a checked version other than yours exists (`checked_version_available`) and whether the entry was merged into another one (`merged_into`). What the jobs remember is kept in `exchange_state.json` in the data folder.
