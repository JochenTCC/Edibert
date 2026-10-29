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

IDs in the user files start with `user_` (tariffs, grid areas and grid rule sets); catalog IDs must not. An ID may exist in only one file; a collision is a load error. Inside the catalog one tariff ID may appear several times as validity versions (section 4a); anywhere else a repeated ID is `ID_COLLISION`. The origin (`catalog` or `user`) is derived at load time and is not stored. A missing user file means "no user entries"; the editor creates it with the current `tariff_format`.

## 2a. Format version (`tariff_format`)

All four files form one **version track**: the root key `tariff_format` (integer) states the format version of the file, and all four share the same current value. Current version: **`1`**.

| Rule | Effect |
|---|---|
| key missing | load error `FORMAT_MISSING` (the file needs the migration) |
| unknown value (not an integer, or a version this release does not read) | load error `FORMAT_UNSUPPORTED` with `value` and the `supported` versions |
| `earnie_data_model` in a tariff file | unknown root field (`TARIFF_UNKNOWN_FIELD`); only the migration reads and removes it, there is no dual read |

**Compatibility rule:** a change that existing files may not satisfy (a new required field, a removed or renamed field, changed meaning) raises `tariff_format` by one and ships a migration step in `edibert.api.migrate` in the same release. Additive optional fields do not raise it. So `valid_from` / `valid_to` / `db_ref` on tariffs and the root key `package` (`0.1.d`) keep version `1`: every existing file stays valid, and an older release rejects the new fields loudly (`TARIFF_UNKNOWN_FIELD`) instead of misreading them. The version is independent of Earnie's `earnie_data_model`; a bump of one never bumps the other. Content dates (`catalog_as_of`, `user_tariffs_as_of`) mean "data as of" and are never used for format decisions.

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
| `valid_from`, `valid_to` | date, optional | first and last day (house time, both inclusive) of this price version; absent = no limit. A slot outside is `TARIFF_NOT_VALID`, never priced with a neighbouring version. Several versions of one ID: section 4a |
| `db_ref` | object, optional | tariff-database entry the tariff was copied from: `database` (`free` / `verified`), `id` (database ID) and `version` (64 hex digits, section 11). Set by "copy from catalog" when the catalog came from a package; the editor shows whether the prices still match that version |

Fields of the existing Earnie catalog (`type`, `fix_cent_kwh`, `k_push_cent`, `monthly_rates`, `settlement_fee_cent_kwh`, `markup_percent`, `prices_include_vat`, `vat_percent`, `settlement_mtu`, `feed_in_fee_factor`, `feed_in_fix_cent`, fee fields, `monthly_seed`, ...) keep their meaning. `vat_percent` is required on every tariff, import and export, gross or net; `0` is allowed and explicit. Net prices get the rate added in step 5, and gross prices need it to be converted to net, so a missing rate is `VAT_PERCENT_MISSING`, never a silent 0 % (decided 2026-10-26; stricter than Earnie memo D3b, which named gross tariffs only). `tiers` and `demand` are rejected with `UNSUPPORTED_FEATURE`. `$comment` is allowed everywhere and ignored. A machine-readable schema is generated by `python -m edibert schema` and stored in `schema/tariff.schema.json`.

## 4a. Validity versions

A provider's price change is a new **version** of the same tariff, not a new tariff. In `tariffs.json` the versions are separate entries with the same `id`, each with `valid_from`; they must not overlap (`TARIFF_VALIDITY_OVERLAP`), and every one but the newest needs `valid_to`. A gap is allowed and fails only for a slot inside it (`TARIFF_NOT_VALID`). Loaded, the ID is one `Tariff`: the newest version, with all versions in date order in `Tariff.periods`; `evaluate` and the price series pick the version per slot by the slot's local date (`api.version_at(tariff, day)`). Fields read without a slot (monthly fees, label, `requires`) come from the newest version.

Versions come from the tariff database only: in `user_tariffs.json` a repeated ID stays `ID_COLLISION`, and "copy from catalog" copies the version valid today without its validity. The editor's catalog list shows the version valid today, else the newest.

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

## 5b. Capacity charge (`capacity_charges`)

**Status:** engine implemented (`0.1.q`, class B in section 7); editor, Home Assistant publishing and the tariff comparison follow (backlog `0.+1`). Models the Austrian grid-fee reform (SNE-G-V, BGBl. II Nr. 299/2026, in force 2027-01-01, introduction per grid area until 2028-06-30): part of the grid fee is billed per month on the **highest quarter-hour average import power** of the calendar month. The SNE-G-V fixes the structure (Netzebene 7: monthly capacity prices in cent per kW, one up to 10 kW and one above, minimum 2 kW); the prices per grid area come with the SNE-T-V and are not final as of 2026-10. All numbers below are placeholders.

### Principles

1. **Part of the grid fee, not of a supplier tariff.** `capacity_charges` is a field of a grid area in `grid_fees.json` or `user_grid_fees.json` (section 5a); the house profile only selects the area. The tariff field `demand` stays rejected (`UNSUPPORTED_FEATURE`).
2. **Never folded into cent/kWh.** The charge depends on the state of the month (the peak so far), so it is not a slot price. The price series keeps its per-slot prices unchanged and carries the charge as a separate block (section 8). An automatic conversion to a per-kWh surcharge would be a silent estimate and is not done.
3. **Edibert is stateless.** The month-to-date peak comes from the caller (smart home or optimizer) on every call; Edibert never stores or guesses it. A missing state is never taken as `0`.
4. **Bands are not `tiers`.** `tiers` means consumption brackets in kWh and stays rejected. Capacity bands are brackets of the monthly peak in kW.

### Fields

`capacity_charges` is a list; entries must not overlap in validity and cover whole calendar months. A month before the first entry starts has no capacity charge (the reform is not introduced yet). A later month that no entry covers is an error (`CAPACITY_CHARGE_MISSING`), as for a missing month in a `monthly_table`: a gap or an outdated list never turns into a charge of zero. Entries left out by `include_status` count as not covering. No list at all means no capacity charge.

| Field | Meaning |
|---|---|
| `id`, `label` | name of the entry |
| `basis` | `monthly_peak_15min` (only value for now): highest clock-aligned 15-minute average import power of the calendar month, local time of the house |
| `min_kw` | minimum assessed power, required, no default (Netzebene 7: 2 kW) |
| `bands[]` | `{up_to_kw, cent_per_kw_month}`, both required, ascending `up_to_kw`, only the last with `up_to_kw: null`; the rate of a band applies to the share of the peak inside it (Netzebene 7: one band up to 10 kW, one above) |
| `valid_from`, `valid_to` | optional dates; `valid_from` is the first and `valid_to` the last day of a month; the introduction date differs per grid area and the rates change yearly |
| `status`, `source`, `note` | as for grid-fee rules; `include_status` of the profile filters entries, a skipped entry is a warning (`GRID_CAPACITY_SKIPPED_STATUS`) |

The rate is stored as the SNE-G-V sets it: cent per kW and month. The month amount is the sum over the bands of the share of `max(peak, min_kw)` inside the band times its rate, rounded commercially to cents (SNE-G-V section 28 (2)). There is no conversion from a yearly rate. The 20 % of contracted power minimum of the SNE-G-V applies to Netzebenen 1 to 6 only and is not modeled; `min_percent_of_contracted` is an unknown field. Amounts are net; Edibert does not add VAT to them (the caller applies the VAT of the grid fee).

Loading checks: `min_kw >= 0`, band rates `>= 0`, `basis` known, catalog entries need a `status` (user entries may omit it and then always apply). Rates that decrease from one band to the next make the charge non-convex and are reported as a warning (`CAPACITY_BANDS_NOT_CONVEX`), because a convex charge is what optimizers can model with linear segments.

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
        { "up_to_kw": 10, "cent_per_kw_month": 150 },
        { "up_to_kw": null, "cent_per_kw_month": 300 }
      ],
      "valid_from": "2027-01-01",
      "valid_to": "2027-12-31",
      "status": "entwurf",
      "source": "placeholder"
    }
  ]
}
```

A complete user grid file with this area: `examples/grid_fee_capacity_example.json`.

### Functions

- `charge_for_month(charges, month, area_id)`: the entry that covers the month, `None` before the first entry starts, else `CAPACITY_CHARGE_MISSING`. `charges` is `GridFee.capacity` (the entries in effect after `include_status`).
- `capacity_charge_eur(charge, peak_kw)`: the net amount of one month for a given peak, with minimum and bands, in EUR rounded to cents. Used by the invoice check.
- `capacity_ladder(charge, state, month, ctx, *, step_kw=None, max_kw=None, require_state=False)`: the remaining cost of the month as a function of the peak, relative to `state`. `state` is `{peak_15min_kw, as_of}` (`CapacityState`, from JSON via `parse_capacity_state`); the local month of `as_of` must be `month`, otherwise `CAPACITY_STATE_MONTH_MISMATCH`. The ladder lists rungs at 0, the minimum, the peak so far and the band limits, and with `step_kw` and `max_kw` (both or neither) every `step_kw` up to `max_kw`. Each rung has `up_to_kw`, `extra_eur` (cost of a month peak there, minus the sunk cost), `marginal_eur_per_kw` (slope above the rung) and `reached`; a rung at or below the larger of `min_kw` and the peak so far (`free_up_to_kw`) is `reached` with `extra_eur: 0` (sunk cost). Without `state` the ladder is absolute (`extra_eur` is the whole month amount, the minimum included) and marked `state: null`; `require_state=True` makes a missing state `CAPACITY_STATE_MISSING`.
- CLI: `python -m edibert capacity --grid-fee … --tz … --month YYYY-MM [--peak-so-far KW --as-of TIME] [--power KW] [--step KW --max KW] [--format json]` prints the month amount for `--power` and the ladder.

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
| B | state dependent | tiers, free allowance, capacity charge (monthly peak, section 5b) | capacity charge supported as a separate block next to the slot prices, never as a slot price; tiers and free allowance later |
| C | behaviour dependent | bonus only if the provider controls charging | note only (`behavior_notes`) |

## 8. Price series (interface)

`tariff_price_series(tariff, ctx, start, end, *, resolution_min=15, market=None, forecast_from=None, grid_fee=None, capabilities=None, forecast_method=None, capacity_state=None)` returns a `PriceSeries` from `start` (inclusive) to `end` (exclusive).

- **Slots:** every 15-minute slot is evaluated in UTC steps, so daylight-saving days have 92 and 100 slots. `start` must be aligned to the resolution and the range must be a multiple of it.
- **Resolution:** 15, 30 or 60 minutes; points are the mean of their 15-minute slots.
- **Market prices:** `market` maps slot starts (cent/kWh, day-ahead, per 15 minutes) to prices; naive keys are local time. A missing price is an error (`PRICE_MISSING`), nothing is carried over. Spot tariffs with `settlement_mtu: 60min` use the mean of the four slots of the clock hour for every slot of that hour.
- **Point:** `start`, `end` (local time with offset), `cent` = `supplier_cent` + `grid_cent` + `vat_cent` (rounded; `grid_cent` is net, and for a gross tariff `supplier_cent` already includes VAT, so `vat_cent` is the VAT on the grid fee), `quality`: `exact`, or `forecast` for slots at or after `forecast_from` when the tariff depends on market prices; `market_cent`: the market price the tariff used (after hourly settlement, mean over the point), `null` for a tariff without market price; `method`: `exact`, or for a forecast point the `forecast_method` the caller named (`mirror`, `hold`, a plug-in name; `null` if none was named).
- **Warnings** (`PriceSeries.warnings`, never errors): `WINDOW_NOT_HOUR_ALIGNED` (a rule window not on a full hour in an hourly settled spot tariff), `REQUIREMENT_UNMET` (only checked when `capabilities` is given), `GRID_RULE_SKIPPED_STATUS`, `GRID_RULE_SKIPPED_NO_QUARTER_HOUR_METER`, `MONTH_RATE_FALLBACK` (section 3, once per requested month), and for capacity charges (section 5b) `GRID_CAPACITY_SKIPPED_STATUS`, `CAPACITY_BANDS_NOT_CONVEX`, `CAPACITY_STATE_UNAVAILABLE`.
- **Market prices for past ranges:** `edibert.api.MarketArchive` / `market_range` deliver the `market` mapping for any range from a per-month cache ([api.md](api.md)).
- **Output:** `PriceSeries.to_dict()` is JSON ready. `python -m edibert series ...` prints it as a table or JSON.

- **Capacity block (section 5b):** for an import tariff whose grid fee carries a capacity charge in effect, `PriceSeries.to_dict()` gets a `capacity` list with one entry per calendar month the range touches and a charge covers: `charge_id`, `month`, `state`, `free_up_to_kw`, `days_remaining` (local days from the later of month start and range start to month end, both inclusive), `ladder[]` with `up_to_kw`, `extra_eur`, `marginal_eur_per_kw`, `reached`, and `unit` ("EUR once per month, net"). `capacity_state` is the measured month-to-date peak. Its month gets the relative ladder with `state` as passed in; a later month starts from a peak of `0` (`state: {peak_15min_kw: 0, as_of: null}`); an earlier month, and every month when no state is given, gets the absolute ladder (`state: null`). The per-slot prices do not change. Export tariffs get no block.

Planned outputs on top of this interface: Home Assistant sensor attributes `raw_today`/`raw_tomorrow` and `forecast`, MQTT (retained, HA discovery), an action `get_rates(start, end, resolution)`, and the capacity block as sensor attributes (`capacity_free_up_to_kw`, `capacity_ladder`, `capacity_days_remaining`) with the month-to-date peak read from a configured entity.

## 9. Errors and language

- Load and evaluation problems are `EdibertError` instances with a stable `code` and `params`; the message is English and meant for logs. The UI shows `error.<code>` from the translation catalog with the params as placeholders (English and German, English authoritative).
- Error codes: `TARIFF_UNKNOWN_FIELD`, `RULE_UNKNOWN_FIELD`, `FIELD_MISSING`, `VALUE_INVALID`, `UNSUPPORTED_FEATURE`, `RULE_VALUE_MISSING`, `GRID_AREA_UNKNOWN`, `VAT_PERCENT_MISSING`, `FILE_INVALID`, `ID_COLLISION`, `ID_PREFIX_MISSING`, `ID_PREFIX_RESERVED`, `GRID_ID_COLLISION`, `GRID_ID_PREFIX_MISSING`, `GRID_ID_PREFIX_RESERVED`, `FORMAT_MISSING`, `FORMAT_UNSUPPORTED`, `MIGRATION_ANSWER_MISSING`, `PRICE_MISSING`, `MARKET_PRICE_REQUIRED`, `HOLIDAY_REGION_MISSING`, `HOLIDAY_REGION_UNKNOWN`, for section 5b `CAPACITY_CHARGE_MISSING`, `CAPACITY_STATE_MISSING`, `CAPACITY_STATE_MONTH_MISMATCH`, for section 4a `TARIFF_NOT_VALID`, `TARIFF_VALIDITY_OVERLAP`, and for section 11 `DB_ID_UNAVAILABLE`, `PACKAGE_FORMAT_UNSUPPORTED`, `PACKAGE_KEY_UNKNOWN`, `PACKAGE_SIGNATURE_INVALID`, `PACKAGE_CONTENT_MISMATCH`, `PACKAGE_IMPORT_CONFLICT` (warning `PACKAGE_EXPIRED`). Migration questions are shown as `question.<code>` (`question.VAT_PERCENT`). Warning codes are listed in section 8. A new code needs an `error.<CODE>` or `warning.<CODE>` text in every catalog (checked by tests).
- Tariff `label` values and supplier/product names are data, not UI text, and are not translated.
- Holiday names come from the `holidays` package in the UI language.

## 10. Examples

See `examples/`.

## 11. Tariff database and catalog packages

**Status:** client part implemented in `0.1.d` (Catalog P1-P5; validity versions in section 4a). The tariff database itself, its review workflow, the signing key and the server are not part of Edibert; the exchange with the server (Catalog P7) is specified in [catalog-exchange.md](catalog-exchange.md).

### Identity and version (Catalog P1)

- **Identity** (`api.tariff_identity(raw, direction)`): `<LAND>/<direction>/<catalog id>`, e.g. `AT/import/at_vkw_strom_duo`; the catalog ID stands for supplier and product. Grid areas: `<LAND>/grid/<area id>` (`api.grid_area_identity`). A user entry (`user_` ID) has none (`DB_ID_UNAVAILABLE`): the database assigns an ID when a tariff is shared. Without `land` there is no identity (`FIELD_MISSING`).
- **Version** (`api.tariff_version(raw, direction)`): SHA-256 (64 hex digits) over the price-relevant values of the **parsed** tariff in canonical JSON: direction, type, land, currency, the base-price fields the type reads (fixed price, monthly rates, or markup, settlement fee and feed-in factors of a spot tariff; a value the type never uses does not count), monthly fees, VAT fields, `settlement_mtu`, monthly rates, rules (without their `id`, `label`, `source`, `note`; all twelve months = no month filter), floor and cap, holiday mode and extra holidays, `valid_from` / `valid_to`. Numbers count as floats, sets and month rows are ordered. Not part of it: ID, label, supplier, notes, `behavior_notes`, `source`, `last_verified`, `regions`, `requires`, `individual`, `db_ref`. So a tariff the editor saves unchanged keeps its version, and every price change makes a new one. Grid areas (`api.grid_area_version(area, rule_sets)`): the area as written plus the rules of its rule set, without ID, label, source, note.
- `api.differs_from_db(raw, direction)`: `None` without `db_ref`, else whether the version no longer equals `db_ref.version`.

### Package format (Catalog P4)

One JSON file:

| Key | Content |
|---|---|
| `edibert_package` | package format, `1` (anything else: `PACKAGE_FORMAT_UNSUPPORTED`) |
| `manifest` | `database` (`free` / `verified`), `package_id`, `issued_at` (ISO 8601 with offset), `valid_until` (date), `tariff_format`, `key_id`, `files` (`tariffs.json` and `grid_fees.json` to the SHA-256 of their canonical JSON) |
| `content` | the two catalog documents `tariffs.json` and `grid_fees.json`, monthly reference curves included |
| `signature` | Ed25519 signature (base64) over the canonical JSON of `manifest` |

Canonical JSON here is `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` in UTF-8. `api.verify_package(document, *, trusted_keys=None, today=None)` checks offline, in this order: format and manifest fields (strict), the key (`PACKAGE_KEY_UNKNOWN`), the signature (`PACKAGE_SIGNATURE_INVALID`), the content hashes (`PACKAGE_CONTENT_MISMATCH`), then the content itself: both documents in the manifest's `tariff_format`, loading like catalog files, and every tariff and area with an identity. A package past `valid_until` stays usable and only warns (`PACKAGE_EXPIRED`): a subscriber keeps the last package received. The trusted public keys are built into Edibert by `key_id` (several at once for a key change); none is built in yet. `trusted_keys` replaces them (tests, a self-hosted database). Signing (`edibert.package.build_package`) needs the private key, which is never in this repository and never on a server.

### Import (Catalog P5)

The package replaces `tariffs.json` and `grid_fees.json`; user files are never touched. `api.plan_package_import(package, local_tariffs, local_grid_fees)` lists the entries the import adds, changes or removes (`import/<id>`, `export/<id>`, `grid/<id>`, `rule_set/<id>`) and the **conflicts**: monthly rates present locally (a tariff's `monthly_rates` row, or a row of a monthly reference curve at the root) that the package lacks or has with another value, keyed `<direction>/<tariff id>/<YYYY-MM>` or `root/<curve>/<YYYY-MM>`. `api.apply_package_import(plan, resolutions)` needs one decision per conflict, `keep_local` or `take_package` (`PACKAGE_IMPORT_CONFLICT` otherwise; an unknown key or choice is `VALUE_INVALID`); a kept row goes into the validity version covering its month, else the newest. The result gets the root key `package` (`database`, `package_id`, `issued_at`, `valid_until`) and is loaded once more before it is returned. `api.write_catalog_pair` writes both files completely to temporary files before either is replaced. The CLI (`python -m edibert package verify|import`) and the standalone editor (sidebar *Import catalog package*) use these functions; an embedding host imports through the API.

