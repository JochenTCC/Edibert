# Tariff format (draft)

**Status:** draft, nothing implemented. Derived from the internal development document `Earnie-Benutzertarife-Entwicklungsdokument.md` (2026-10-11). Prices in all examples are placeholders.

## 1. Principles

1. **Additive.** The format extends the existing Earnie `tariffs.json` entries. Existing entries stay valid.
2. **One mechanism for time dependence:** `rules[]` with calendar filters (validity, months, weekdays, time of day) and an effect. The first matching rule wins.
3. **Rules and price series are separate.** A tariff is compiled to a price series per slot; the series is the only interface to consumers (optimizer, Home Assistant, MQTT).
4. **No silent fallbacks.** Features the engine does not support yet (`tiers`, `applies_to` other than `"main"`) are rejected at load time.
5. **Readable.** Weekdays and months may be words in addition to numbers.

## 2. Files

| File | Content | Written by |
|---|---|---|
| `tariffs.json` | catalog (`import_tariffs`, `export_tariffs`) | catalog package / seed |
| `user_tariffs.json` | tariffs created by the user, same structure | editor |
| `grid_fees.json` | grid-area catalog (`rule_sets`, `areas`, Earnie shape), section 5a | catalog package / seed |
| `user_grid_fees.json` | grid areas created by the user, same structure | editor, `edibert.api.save_user_grid_area` |

IDs in the user files start with `user_` (tariffs, grid areas and grid rule sets); catalog IDs must not. An ID may exist in only one file; a collision is a load error. The origin (`catalog` or `user`) is derived at load time and is not stored. A missing user file means "no user entries"; the editor creates it with the current `tariff_format`.

## 2a. Format version (`tariff_format`)

All four files form one **version track**: the root key `tariff_format` (integer) states the format version of the file, and all four share the same current value. Current version: **`1`**.

| Rule | Effect |
|---|---|
| key missing | load error `FORMAT_MISSING` (the file needs the migration) |
| unknown value (not an integer, or a version this release does not read) | load error `FORMAT_UNSUPPORTED` with `value` and the `supported` versions |
| `earnie_data_model` in a tariff file | unknown root field (`TARIFF_UNKNOWN_FIELD`); only the migration reads and removes it, there is no dual read |

**Compatibility rule:** a change that existing files may not satisfy (a new required field, a removed or renamed field, changed meaning) raises `tariff_format` by one and ships a migration step in `edibert.api.migrate` in the same release. Additive optional fields do not raise it. The version is independent of Earnie's `earnie_data_model`; a bump of one never bumps the other. Content dates (`catalog_as_of`, `user_tariffs_as_of`) mean "data as of" and are never used for format decisions.

**Migration** (`edibert.api.plan_migration` / `migrate`, pure functions: documents in, documents out; the caller reads and writes the files and keeps the backup). From untagged files to version 1:

1. tag every untagged file with `tariff_format: 1` and remove `earnie_data_model` from every tariff file;
2. create user grid areas in `user_grid_fees.json` from areas handed in by the caller (Earnie: one area `user_<profile_id>` per house profile with an own base price, the same price for both metering types, no rule set); an identical area already present is no change, one with other values is a blocker (`GRID_ID_COLLISION`);
3. ask for `vat_percent` on every user tariff without one, gross or net (question `VAT_PERCENT`, prefill AT 20, DE 19, CH 8.1 by the tariff's `land`, none otherwise); the rate is written only from an answer, never from the prefill.

The migrated files must load; the first load error per file is reported as a blocker with its error code (for example `VAT_PERCENT_MISSING` for a catalog tariff without a rate, which is not asked because catalogs are not user data). A run with blockers changes nothing. Running the migration on migrated files changes nothing.

## 3. Evaluation order per slot (import)

```
1. base         fixed:  fix_cent_kwh
                spot:   EPEX * (1 + markup_percent/100) + settlement_fee_cent_kwh
                table:  monthly_rates(year, month)
2. rules        first matching rule changes the base (absolute_cent | add_cent | percent_off)
3. floor/cap    price_floor_cent_kwh <= price <= price_cap_cent_kwh (optional)
4. grid fee     work price of the grid area the house profile selects (section 5a), added
5. VAT          net prices:   (supplier part + grid fee) * (1 + vat_percent/100)
                gross prices: supplier part + grid fee * (1 + vat_percent/100)
```

The grid fee is always net, so with gross prices only the grid fee gets the VAT (as in Earnie, `grid_fee_on_tariff_basis`). Until `0.1.i` Edibert added it without VAT.

Export tariffs use the same steps 1 to 3 and 5 (no grid fee). Spot export base: `EPEX - feed_in_fee_factor * abs(EPEX) - settlement_fee_cent_kwh + feed_in_fix_cent`.

All steps are implemented in `edibert.tariff.evaluate`; the final price is rounded to 4 decimals. The grid fee (step 4) applies to import tariffs only and is passed in as `grid_fee`; export tariffs ignore it.

**Missing month in a `monthly_table`** (import and export, Earnie's order since `0.1.g`): the rate of the slot's local calendar month; if the table has none, the same month of the previous year (`prior_year`); if that is missing too, the previous calendar month (`prior_month`; January takes December of the year before). No further step: a month that needs a second step back, or a month before the table starts with no entry one year or one month earlier, is `PRICE_MISSING`. Every fallback is reported as the coded warning `MONTH_RATE_FALLBACK` (`tariff_id`, `direction`, `month`, `used_month`, `rule`): on `PriceResult.warnings` per slot and once per requested month on `PriceSeries.warnings`, also when a 72-hour window only reaches into the missing month. The fallback rate goes through steps 2 to 5 like any rate.

**Differences from Earnie:** the fallback is a coded warning on the result, not a log line printed once per process. Fields Edibert does not know are errors, not ignored.

## 4. New tariff fields

| Field | Type | Meaning |
|---|---|---|
| `rules[]` | list | time rules, see section 5 |
| `price_floor_cent_kwh` | number, optional | lower bound after rules (export: `0` = never negative) |
| `price_cap_cent_kwh` | number, optional | upper bound after rules |
| `requires[]` | list, optional | `smart_meter`, `quarter_hour_meter`, `separate_meter`, `controllable_device`; unmet = warning, not an error |
| `behavior_notes` | text, optional | behaviour-bound conditions, display only |
| `source`, `last_verified` | text, date | origin of the price sheet and date of last check |
| `holidays` | object, optional | `{"treat_as": "sunday" \| "weekday" \| "own"}`, default `sunday` |
| `extra_holiday_dates` | list of dates, optional | additional days that count as holidays for this tariff |
| `individual` | boolean, optional | tariff is personal (special conditions); never uploaded |
| `regions[]` | list, optional | federal states / cantons the tariff is offered in, as subdivision codes of the `holidays` package (the codes of the house field `region`, e.g. `["8"]` for Vorarlberg); needs `land`; an empty list, a duplicate or an unknown code is `VALUE_INVALID`, a missing `land` is `FIELD_MISSING`; absent = the whole land. Used to filter catalog lists, never in the price calculation. Areas below a federal state (e.g. Kleinwalsertal) cannot be expressed |
| `applies_to` | string, reserved | only `"main"` is allowed |

Fields of the existing Earnie catalog (`type`, `fix_cent_kwh`, `k_push_cent`, `monthly_rates`, `settlement_fee_cent_kwh`, `markup_percent`, `prices_include_vat`, `vat_percent`, `settlement_mtu`, `feed_in_fee_factor`, `feed_in_fix_cent`, fee fields, `monthly_seed`, ...) keep their meaning. `vat_percent` is required on every tariff, import and export, gross or net; `0` is allowed and explicit. Net prices get the rate added in step 5, and gross prices need it to be converted to net, so a missing rate is `VAT_PERCENT_MISSING`, never a silent 0 % (decided 2026-10-26; stricter than Earnie memo D3b, which named gross tariffs only). `tiers` and `demand` are rejected with `UNSUPPORTED_FEATURE`. `$comment` is allowed everywhere and ignored. A machine-readable schema is generated by `python -m edibert schema` and stored in `schema/tariff.schema.json`.

## 5. Rule

| Field | Meaning |
|---|---|
| `id`, `label` | name of the rule |
| `valid_from`, `valid_to` | dates |
| `months` | `[1..12]` or `null` |
| `weekdays` | `[0..6]` (Mon=0), day names (`mon`..`sun`), groups `"weekday"` / `"weekend"`, and the token `"holiday"`; a single string or a list; see section 6 |
| `time` | `{from, to}` as `HH:MM`, `from` inclusive and `to` exclusive, may wrap midnight (`to` may be `24:00`); `from` = `to` is invalid |
| `effect` | `{mode, value}`; `mode` is `absolute_cent` (replace price), `add_cent`, `percent_off` |
| `when_market_cent_kwh` | optional filter on the slot's EPEX price: `{below: x}` or `{above: x}` |
| `requires` | as for tariffs, applies to the rule |

Rules act on the 15-minute slot, also for tariffs with `settlement_mtu: 60min` (the spot component remains the hourly mean). Local time of the house profile applies.

## 5a. Grid fee (`netznutzung`)

The grid-fee work price (Netznutzungsentgelt, net, cent/kWh) is not part of a tariff. The **house profile selects** a grid area and states the metering facts of the house; the **grid areas are defined** in the tariff-track files `grid_fees.json` (catalog) and `user_grid_fees.json` (own values). The shapes follow Earnie, so both price identically (verified against Earnie on all 14 catalog areas).

House-profile field `netznutzung`:

| Field | Meaning |
|---|---|
| `area_id` | required: ID of a catalog or user grid area. There is no implicit "no grid fee"; a house without a grid fee selects a user area with `0` |
| `power_metering` | `unmetered_power` (default) or `metered_power`; selects the area's base price |
| `quarter_hour_meter` | quarter-hour smart meter available; rules that require it are skipped otherwise |
| `include_status` | rule statuses in effect, default `["verordnet"]` (`entwurf`, `illustrativ` must be included on purpose) |

Other fields are errors. The former own values `base_cent_kwh`, `rules`, `holidays` and `extra_holiday_dates` are not allowed any more; they live in a user grid area (the migration moves an own base price there, section 2a).

Grid file (`grid_fees.json`, `user_grid_fees.json`): root keys `tariff_format`, `description`, `rule_sets` (rule-set ID to a list of rules) and `areas`. An area has `id`, `label`, `land`, `base_cent_kwh` (`{unmetered_power, metered_power}`, both required), `rule_set` (optional, a rule set of the same file) and `source`. Rules have the fields of tariff rules except `when_market_cent_kwh`, plus `status`, `source`, `note`; `status` is required in the catalog and optional in the user file (a user rule without status always applies). A holiday counts as a Sunday for grid rules. In the user file area and rule-set IDs start with `user_`. An own flat work price is an area with the same price for both metering types and no rule set (`edibert.api.flat_user_grid_area`).

The base price comes from the selected area by metering type, and the area's rule set applies. Rules whose `status` is not included or whose `quarter_hour_meter` requirement is not met are skipped and reported as warnings. An included rule without a value (`effect.value` is `null`) is an error (`RULE_VALUE_MISSING`); an unknown area is `GRID_AREA_UNKNOWN`. First matching rule wins. Section 14a EnWG module 3 (low/standard/high level) is modeled as base price = standard level plus one rule per other level (see `examples/grid_fee_modul3_example.json`, a user grid file, and `examples/netznutzung_modul3_example.json`, the selection).

## 5b. Capacity charge (`capacity_charges`) — draft, not implemented

**Status:** planned (backlog `0.+1`, class B in section 7). Nothing of this section is implemented; field names and codes may still change. Models the Austrian grid-fee reform (SNE-G-V, from 2027 per grid area): part of the grid fee is billed per month on the **highest quarter-hour average import power** of the calendar month. The regulation and the per-area prices are drafts as of 2026-10; all numbers below are placeholders.

### Principles

1. **Part of the grid fee, not of a supplier tariff.** `capacity_charges` is a field of a grid area in `grid_fees.json` or `user_grid_fees.json` (section 5a); the house profile only selects the area. The tariff field `demand` stays rejected (`UNSUPPORTED_FEATURE`).
2. **Never folded into cent/kWh.** The charge depends on the state of the month (the peak so far), so it is not a slot price. The price series keeps its per-slot prices unchanged and carries the charge as a separate block (section 8). An automatic conversion to a per-kWh surcharge would be a silent estimate and is not done.
3. **Edibert is stateless.** The month-to-date peak comes from the caller (smart home or optimizer) on every call; Edibert never stores or guesses it. A missing state is never taken as `0`.
4. **Bands are not `tiers`.** `tiers` means consumption brackets in kWh and stays rejected. Capacity bands are brackets of the monthly peak in kW.

### Fields

`capacity_charges` is a list; entries must not overlap in validity. For a month with at least one entry in the list but none that covers it, evaluation is an error (`CAPACITY_CHARGE_MISSING`), as for a missing month in a `monthly_table`. No list at all means no capacity charge.

| Field | Meaning |
|---|---|
| `id`, `label` | name of the entry |
| `basis` | `monthly_peak_15min` (only value for now): highest clock-aligned 15-minute average import power of the calendar month, local time of the house |
| `min_kw` | minimum assessed power, required, no default (draft: 2 kW) |
| `min_percent_of_contracted` | optional; the minimum is then the larger of `min_kw` and this share of `contracted_kw` from the house profile; `contracted_kw` missing = error (`FIELD_MISSING`) |
| `bands[]` | `{up_to_kw, eur_per_kw_year}`, ascending `up_to_kw`, the last with `up_to_kw: null`; the rate of a band applies to the share of the peak inside it (draft: one band up to 10 kW, one above) |
| `valid_from`, `valid_to` | dates; the introduction date differs per grid area and the rates change yearly |
| `status`, `source`, `note` | as for grid-fee rules; `include_status` of the profile filters entries, a skipped entry is a warning (`GRID_CAPACITY_SKIPPED_STATUS`) |

The rate is stored as printed on the price sheet (EUR per kW and year). **Open:** the monthly amount is assumed to be `peak_kw * eur_per_kw_year / 12` per band; the exact billing formula is taken from the final SNE-V once published and this line is updated. Net amounts; VAT follows the tariff's `prices_include_vat` and `vat_percent` like the work price.

Loading checks: `min_kw >= 0`, band rates `>= 0`. Rates that decrease from one band to the next make the charge non-convex and are reported as a warning (`CAPACITY_BANDS_NOT_CONVEX`), because a convex charge is what optimizers can model with linear segments.

Example (a user grid area, placeholders):

```json
{
  "id": "user_home",
  "base_cent_kwh": { "unmetered_power": 4.5, "metered_power": 4.5 },
  "capacity_charges": [
    {
      "id": "lp_2027",
      "basis": "monthly_peak_15min",
      "min_kw": 2.0,
      "bands": [
        { "up_to_kw": 10, "eur_per_kw_year": 19.0 },
        { "up_to_kw": null, "eur_per_kw_year": 28.0 }
      ],
      "valid_from": "2027-01-01",
      "valid_to": "2027-12-31",
      "status": "entwurf",
      "source": "SNE-V 2027 draft, grid area XY"
    }
  ]
}
```

### Functions

- `capacity_charge_eur(charge, peak_kw)`: the net amount of one month for a given peak, with minimum and bands. Used by the invoice check.
- `capacity_ladder(charge, state, month, *, step_kw=None)`: the remaining cost of the month as a function of the peak, relative to `state`. `state` is `{peak_15min_kw, as_of}` and must belong to `month`, otherwise `CAPACITY_STATE_MONTH_MISMATCH`. The ladder lists the break points (minimum, peak so far, band limits) and optionally rungs every `step_kw`; a rung at or below the larger of `min_kw` and the peak so far is `reached` with `extra_eur: 0` (sunk cost). Without `state` the ladder is absolute and marked `state: null`; a caller that needs the relative ladder gets `CAPACITY_STATE_MISSING`.

The state is **measured**, not planned: the meter's clock-aligned quarter-hour averages decide, a short burst above a band limit does not. A caller may pass a planned peak as state to see the ladder after a deliberate exceedance (what-if); Edibert does not distinguish the two.

### Capability `quarter_hour_meter`

The grid operator bills the peak also when the customer opted out of 15-minute data. A capacity charge is therefore never skipped for a missing `quarter_hour_meter`; the house only cannot supply the state then, which the warning `CAPACITY_STATE_UNAVAILABLE` says.

## 6. Holidays

Holidays come from the `holidays` package (MIT, offline), category `PUBLIC`, by country (`AT`, `DE`, `CH`) and region (federal state or canton). The pricing context needs `land` and `region` whenever holidays can change a result; a missing region is an error (`HOLIDAY_REGION_MISSING`), an unknown one too (`HOLIDAY_REGION_UNKNOWN`).

**When is a calendar needed?** A tariff needs one if it has a rule with a `weekdays` filter and `treat_as` is not `"weekday"`, or if any rule uses the `"holiday"` token. Tariffs without weekday filters never need a region.

- `treat_as: "sunday"` (default): a holiday counts as a Sunday for weekday filters (`weekend`, `[6]`, `sun`, but not `weekday`); the `"holiday"` token matches too.
- `treat_as: "weekday"`: holidays get no special treatment for the day-of-week filters (the real weekday applies); the `"holiday"` token still matches.
- `treat_as: "own"`: on a holiday, a rule with a `weekdays` filter applies only if that filter contains `"holiday"`; rules without a weekday filter apply as usual. Use it when a tariff has its own holiday price.

`extra_holiday_dates` adds days (for example 24 and 31 December) that count as holidays for this tariff only.

## 7. Feature classes

| Class | Property | Examples | Engine |
|---|---|---|---|
| A | price is a function of the slot | fixed, HT/NT, spot with markups, floor/cap, §14a Modul 3, no pay at negative price | supported |
| B | state dependent | tiers, free allowance, capacity charge (monthly peak, section 5b) | later; capacity charge planned as a separate block next to the slot prices, never as a slot price |
| C | behaviour dependent | bonus only if the provider controls charging | note only (`behavior_notes`) |

## 8. Price series (interface)

`tariff_price_series(tariff, ctx, start, end, *, resolution_min=15, market=None, forecast_from=None, grid_fee=None, capabilities=None, forecast_method=None)` returns a `PriceSeries` from `start` (inclusive) to `end` (exclusive).

- **Slots:** every 15-minute slot is evaluated in UTC steps, so daylight-saving days have 92 and 100 slots. `start` must be aligned to the resolution and the range must be a multiple of it.
- **Resolution:** 15, 30 or 60 minutes; points are the mean of their 15-minute slots.
- **Market prices:** `market` maps slot starts (cent/kWh, day-ahead, per 15 minutes) to prices; naive keys are local time. A missing price is an error (`PRICE_MISSING`), nothing is carried over. Spot tariffs with `settlement_mtu: 60min` use the mean of the four slots of the clock hour for every slot of that hour.
- **Point:** `start`, `end` (local time with offset), `cent` = `supplier_cent` + `grid_cent` + `vat_cent` (rounded; `grid_cent` is net, and for a gross tariff `supplier_cent` already includes VAT, so `vat_cent` is the VAT on the grid fee), `quality`: `exact`, or `forecast` for slots at or after `forecast_from` when the tariff depends on market prices; `market_cent`: the market price the tariff used (after hourly settlement, mean over the point), `null` for a tariff without market price; `method`: `exact`, or for a forecast point the `forecast_method` the caller named (`mirror`, `hold`, a plug-in name; `null` if none was named).
- **Warnings** (`PriceSeries.warnings`, never errors): `WINDOW_NOT_HOUR_ALIGNED` (a rule window not on a full hour in an hourly settled spot tariff), `REQUIREMENT_UNMET` (only checked when `capabilities` is given), `GRID_RULE_SKIPPED_STATUS`, `GRID_RULE_SKIPPED_NO_QUARTER_HOUR_METER`, `MONTH_RATE_FALLBACK` (section 3, once per requested month).
- **Market prices for past ranges:** `edibert.api.MarketArchive` / `market_range` deliver the `market` mapping for any range from a per-month cache ([api.md](api.md)).
- **Output:** `PriceSeries.to_dict()` is JSON ready. `python -m edibert series ...` prints it as a table or JSON.

- **Capacity block (planned, section 5b):** when the grid fee carries a capacity charge, `PriceSeries.to_dict()` gets a `capacity` list with one entry per calendar month the range touches: `month`, `state` (as passed in, or `null`), `free_up_to_kw`, `days_remaining`, `ladder[]` with `up_to_kw`, `extra_eur`, `marginal_eur_per_kw`, `reached`, and `unit` ("EUR once per month, net"). The per-slot prices do not change. A month after the state's month starts with a peak of `0`.

Planned outputs on top of this interface: Home Assistant sensor attributes `raw_today`/`raw_tomorrow` and `forecast`, MQTT (retained, HA discovery), an action `get_rates(start, end, resolution)`, and the capacity block as sensor attributes (`capacity_free_up_to_kw`, `capacity_ladder`, `capacity_days_remaining`) with the month-to-date peak read from a configured entity.

## 9. Errors and language

- Load and evaluation problems are `EdibertError` instances with a stable `code` and `params`; the message is English and meant for logs. The UI shows `error.<code>` from the translation catalog with the params as placeholders (English and German, English authoritative).
- Error codes: `TARIFF_UNKNOWN_FIELD`, `RULE_UNKNOWN_FIELD`, `FIELD_MISSING`, `VALUE_INVALID`, `UNSUPPORTED_FEATURE`, `RULE_VALUE_MISSING`, `GRID_AREA_UNKNOWN`, `VAT_PERCENT_MISSING`, `FILE_INVALID`, `ID_COLLISION`, `ID_PREFIX_MISSING`, `ID_PREFIX_RESERVED`, `GRID_ID_COLLISION`, `GRID_ID_PREFIX_MISSING`, `GRID_ID_PREFIX_RESERVED`, `FORMAT_MISSING`, `FORMAT_UNSUPPORTED`, `MIGRATION_ANSWER_MISSING`, `PRICE_MISSING`, `MARKET_PRICE_REQUIRED`, `HOLIDAY_REGION_MISSING`, `HOLIDAY_REGION_UNKNOWN`. Migration questions are shown as `question.<code>` (`question.VAT_PERCENT`). Planned codes of section 5b (not implemented): errors `CAPACITY_CHARGE_MISSING`, `CAPACITY_STATE_MISSING`, `CAPACITY_STATE_MONTH_MISMATCH`; warnings `GRID_CAPACITY_SKIPPED_STATUS`, `CAPACITY_BANDS_NOT_CONVEX`, `CAPACITY_STATE_UNAVAILABLE`. Warning codes are listed in section 8. A new code needs an `error.<CODE>` or `warning.<CODE>` text in every catalog (checked by tests).
- Tariff `label` values and supplier/product names are data, not UI text, and are not translated.
- Holiday names come from the `holidays` package in the UI language.

## 10. Examples

See `examples/`.
