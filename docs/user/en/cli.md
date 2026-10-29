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

## Capacity charge

```bash
python -m edibert capacity --grid-fee house_grid.json --user-grid-fees examples/grid_fee_capacity_example.json --tz Europe/Vienna --month 2027-01 --peak-so-far 4.2 --as-of 2027-01-14T18:00 --power 12
```

For grid areas with a capacity charge (a monthly price per kW of the highest quarter hour of the month). The command shows the charge of the month `--month` (`YYYY-MM`): with `--power` the month amount for that peak, and a table of what each higher peak would cost on top. `--peak-so-far` is the highest measured quarter hour of the month so far, in kW, and needs `--as-of`, the time of that reading; without it the table shows the full month amounts. `--step 2 --max 16` adds rows every 2 kW up to 16 kW. `--format json` prints the table as JSON. Amounts are net. A month without a matching entry in the grid area stops the command with an error; for a month before the charge starts the command says that there is none.

## Catalog package

```bash
python -m edibert package verify package.json
python -m edibert package import package.json --catalog tariffs.json --grid-catalog grid_fees.json [--dry-run]
```

A catalog package is a signed file from the tariff database that replaces the catalog files `tariffs.json` and `grid_fees.json`. Your own tariffs (`user_tariffs.json`) and grid areas stay unchanged. `verify` checks the signature and the content and shows the package; a changed or damaged package is refused. A package past its validity date still works, with a note that it gets no more updates.

`import` first lists what changes (new, changed and removed entries). If you entered monthly rates yourself that the package does not have or has with another value, each one is listed as a conflict, for example `import/at_example/2026-11`, and the import stops until you decide: `--keep-local KEY` keeps your value, `--take-package KEY` takes the package's (both repeatable). `--dry-run` only shows the list. If writing fails, the old catalog files stay.

## Publish

```bash
python -m edibert publish --data-dir edibert_data [--once] [--dry-run] [--catalog tariffs.json] [--config publish.json]
```

Publishes the tariffs of `publish.json` to an MQTT broker; see [Publishing](publishing.md). Exit code 1 means that at least one tariff went offline (for example because no market prices were available).

## Schema

`python -m edibert schema` prints the JSON Schema of a tariff, for editors and tools.
