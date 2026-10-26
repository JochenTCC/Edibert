# Command line

Add `--lang de` before the command for German output.

## Price of one slot

```bash
python -m edibert price --tariff examples/spot_evening_surcharge_cap.json \
    --at 2026-12-15T18:00 --tz Europe/Vienna --epex 10
```

Prints base price, applied rule, grid fee and final price. Tariffs with rules for certain days need `--land` and `--region`, because holidays can change the price. A market-price tariff needs `--epex` (cent/kWh).

## Price series

```bash
python -m edibert series --tariff examples/spot_evening_surcharge_cap.json \
    --from 2026-12-15T00:00 --to 2026-12-16T00:00 --tz Europe/Vienna \
    --market-csv market.csv --resolution 60
```

`--resolution` is 15, 30 or 60 minutes. The market file has one line per quarter hour: `timestamp,cent_kwh`. A missing price stops the command with an error. `--format json` prints the full series. `--has smart_meter` (repeatable) names what the house has and enables the requirement check.

## Grid fee

Add `--grid-fee house_grid.json` to include a grid fee. The file holds the `netznutzung` object of the house profile, which selects a grid area by `area_id` (see `examples/netznutzung_modul3_example.json`). The area comes from `--grid-catalog grid_fees.json` (catalog areas) or `--user-grid-fees user_grid_fees.json` (own areas with IDs starting with `user_`, see `examples/grid_fee_modul3_example.json`); both may be given. An unknown area stops the command with an error.

## Publish

```bash
python -m edibert publish --data-dir edibert_data [--once] [--dry-run] [--catalog tariffs.json] [--config publish.json]
```

Publishes the tariffs of `publish.json` to an MQTT broker; see [Publishing](publishing.md). Exit code 1 means that at least one tariff went offline (for example because no market prices were available).

## Schema

`python -m edibert schema` prints the JSON Schema of a tariff, for editors and tools.
