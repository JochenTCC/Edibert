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

IDs in `user_tariffs.json` start with `user_`. An ID may exist in only one file; a collision is a load error. The origin (`catalog` or `user`) is derived at load time and is not stored.

## 3. Evaluation order per slot (import)

```
1. base         fixed:  fix_cent_kwh
                spot:   EPEX * (1 + markup_percent/100) + settlement_fee_cent_kwh
                table:  monthly_rates(year, month)
2. rules        first matching rule changes the base (absolute_cent | add_cent | percent_off)
3. floor/cap    price_floor_cent_kwh <= price <= price_cap_cent_kwh (optional)
4. grid fee     work price from the house profile (own rules), added
5. VAT          * (1 + vat_percent/100) if prices_include_vat is false
```

Export tariffs use the same steps 1 to 3 and 5 (no grid fee).

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
| `applies_to` | string, reserved | only `"main"` is allowed |

## 5. Rule

| Field | Meaning |
|---|---|
| `id`, `label` | name of the rule |
| `valid_from`, `valid_to` | dates |
| `months` | `[1..12]` or `null` |
| `weekdays` | `[0..6]` (Mon=0), or `"weekday"`, `"weekend"`, `"holiday"`, or day names |
| `time` | `{from, to}` as `HH:MM`, may wrap midnight; minutes allowed (15-minute slots) |
| `effect` | `{mode, value}`; `mode` is `absolute_cent` (replace price), `add_cent`, `percent_off` |
| `when_market_cent_kwh` | optional filter on the slot's EPEX price: `{below: x}` or `{above: x}` |
| `requires` | as for tariffs, applies to the rule |

Rules act on the 15-minute slot, also for tariffs with `settlement_mtu: 60min` (the spot component remains the hourly mean). Local time of the house profile applies.

## 6. Holidays

Holidays come from the `holidays` package (MIT, offline), category `PUBLIC`, by country and region (federal state or canton, ISO 3166-2). The house profile needs a `region` if any tariff uses holiday logic; a missing region is a load error.

- `treat_as: "sunday"` (default): a holiday matches `weekend`, `[6]` and `"holiday"`, but not `weekday`.
- `treat_as: "weekday"`: holidays are ignored for weekday filters.
- `treat_as: "own"`: holidays match only rules with `"holiday"` in `weekdays`.

## 7. Feature classes

| Class | Property | Examples | Engine |
|---|---|---|---|
| A | price is a function of the slot | fixed, HT/NT, spot with markups, floor/cap, §14a Modul 3, no pay at negative price | supported |
| B | state dependent | tiers, free allowance, capacity charge | later, evaluation first |
| C | behaviour dependent | bonus only if the provider controls charging | note only (`behavior_notes`) |

## 8. Price series (interface)

`tariff_price_series(tariff, slots, epex, house)` returns one price per slot for a chosen horizon and resolution (15, 30 or 60 minutes), for import and export. Each point may carry components (energy, grid, levies) and a quality flag (`complete`, `exact`, `forecast`).

Planned outputs: Home Assistant sensor attributes `raw_today`/`raw_tomorrow` and `forecast`, MQTT (retained, HA discovery), and an action `get_rates(start, end, resolution)`.

## 9. Errors and language

- Load and evaluation problems are `EdbertError` instances with a stable `code` and `params`; the message is English and meant for logs. The UI shows `error.<code>` from the translation catalog with the params as placeholders (English and German, English authoritative).
- Codes: `RULE_UNKNOWN_FIELD` (field, rule_id), `UNSUPPORTED_FEATURE` (feature, tariff_id), `HOLIDAY_REGION_MISSING`, `PRICE_MISSING` (slot, tariff_id), `ID_COLLISION` (tariff_id). A new code needs an `error.<CODE>` text in every catalog.
- Tariff `label` values and supplier/product names are data, not UI text, and are not translated.
- Holiday names come from the `holidays` package in the UI language.

## 10. Examples

See `examples/`.
