"""Prices from the example files (placeholder prices) and the documented rule semantics."""

import pytest
from conftest import EXPORT, at, load_example, make

from edibert.errors import EdibertError, ErrorCode
from edibert.tariff import evaluate, price_cent


def test_day_night_weekday_night_and_weekend(ctx_de):
    tariff = make(load_example("fixed_day_night.json"))
    assert price_cent(tariff, at("2026-10-12 12:00"), ctx_de) == 32.0  # Monday noon: base
    assert price_cent(tariff, at("2026-10-12 23:00"), ctx_de) == 25.0  # Monday night
    assert price_cent(tariff, at("2026-10-17 12:00"), ctx_de) == 27.0  # Saturday noon
    assert price_cent(tariff, at("2026-10-17 23:00"), ctx_de) == 25.0  # first matching rule wins


def test_night_window_includes_start_and_excludes_end(ctx_de):
    tariff = make(load_example("fixed_day_night.json"))
    assert price_cent(tariff, at("2026-10-13 05:45"), ctx_de) == 25.0
    assert price_cent(tariff, at("2026-10-13 06:00"), ctx_de) == 32.0
    assert price_cent(tariff, at("2026-10-13 21:45"), ctx_de) == 32.0
    assert price_cent(tariff, at("2026-10-13 22:00"), ctx_de) == 25.0


def test_holiday_counts_as_sunday_by_default(ctx_de):
    tariff = make(load_example("fixed_day_night.json"))
    assert price_cent(tariff, at("2026-12-25 12:00"), ctx_de) == 27.0  # Friday, Christmas Day


def test_holiday_mode_weekday_ignores_holidays(ctx_de):
    tariff = make(load_example("fixed_day_night.json"), holidays={"treat_as": "weekday"})
    assert price_cent(tariff, at("2026-12-25 12:00"), ctx_de) == 32.0
    assert tariff.needs_calendar is False


def test_holiday_mode_own_suppresses_weekday_rules_on_holidays(ctx_de):
    tariff = make(load_example("fixed_day_night.json"), holidays={"treat_as": "own"})
    # the "weekend" rule has a weekday filter without the holiday token, so it does not apply
    assert price_cent(tariff, at("2026-12-25 12:00"), ctx_de) == 32.0
    assert price_cent(tariff, at("2026-12-25 23:00"), ctx_de) == 25.0  # night rule has no filter


def test_holiday_token_rule(ctx_de):
    raw = load_example("fixed_day_night.json")
    raw["rules"] = [
        {"id": "holiday", "weekdays": ["holiday"], "effect": {"mode": "absolute_cent", "value": 20.0}}
    ]
    tariff = make(raw, holidays={"treat_as": "weekday"})
    assert price_cent(tariff, at("2026-12-25 12:00"), ctx_de) == 20.0
    assert price_cent(tariff, at("2026-12-24 12:00"), ctx_de) == 32.0


def test_extra_holiday_dates(ctx_de):
    tariff = make(load_example("fixed_day_night.json"), extra_holiday_dates=["2026-12-24"])
    assert price_cent(tariff, at("2026-12-24 12:00"), ctx_de) == 27.0  # Thursday counts as holiday


def test_spot_markup_cap_vat_and_winter_surcharge(ctx_at):
    tariff = make(load_example("spot_evening_surcharge_cap.json"))
    assert price_cent(tariff, at("2026-12-15 18:00"), ctx_at, epex_cent=10.0) == 16.56  # (10*1.03+1.5+2)*1.2
    assert price_cent(tariff, at("2026-07-15 18:00"), ctx_at, epex_cent=10.0) == 14.16  # no surcharge
    capped = evaluate(tariff, at("2026-12-15 18:00"), ctx_at, epex_cent=40.0)
    assert capped.after_rule_cent == pytest.approx(44.7)
    assert capped.after_limits_cent == 30.0
    assert capped.cent == 36.0  # cap applies before VAT


def test_spot_tariff_needs_a_market_price(ctx_at):
    tariff = make(load_example("spot_evening_surcharge_cap.json"))
    slot = at("2026-12-15 18:00")
    with pytest.raises(EdibertError) as err:
        price_cent(tariff, slot, ctx_at)
    assert err.value.code == ErrorCode.MARKET_PRICE_REQUIRED


def test_export_pays_nothing_at_negative_price(ctx_de):
    tariff = make(load_example("export_no_pay_at_negative_price.json"), EXPORT)
    assert price_cent(tariff, at("2026-06-20 13:00"), ctx_de, epex_cent=-2.0) == 0.0
    assert price_cent(tariff, at("2026-06-20 13:00"), ctx_de, epex_cent=5.0) == 7.8
    slot = at("2026-06-20 13:00")
    with pytest.raises(EdibertError) as err:
        price_cent(tariff, slot, ctx_de)
    assert err.value.code == ErrorCode.MARKET_PRICE_REQUIRED


def test_export_spot_formula_and_floor(ctx_plain):
    raw = {
        "id": "x", "type": "spot_hourly", "supplier_id": "s", "feed_in_fee_factor": 0.19,
        "settlement_fee_cent_kwh": 0.5, "feed_in_fix_cent": 0.1, "price_floor_cent_kwh": 0, "vat_percent": 0,
    }  # fmt: skip
    tariff = make(raw, EXPORT)
    assert price_cent(tariff, at("2026-06-20 13:00"), ctx_plain, epex_cent=10.0) == pytest.approx(7.7, abs=1e-4)
    assert price_cent(tariff, at("2026-06-20 13:00"), ctx_plain, epex_cent=-4.0) == 0.0


def test_matches_earnie_documented_examples(ctx_plain):
    # Documented in the Earnie user docs: aWATTar AT (5 ct -> 7.98) and VKW Dynamisch (10 ct -> 13.44)
    awattar = make({"id": "a", "type": "spot_hourly", "supplier_id": "s", "settlement_fee_cent_kwh": 1.5,
                    "markup_percent": 3.0, "prices_include_vat": False, "vat_percent": 20.0})  # fmt: skip
    vkw = make({"id": "v", "type": "spot_hourly", "supplier_id": "s", "settlement_fee_cent_kwh": 1.2,
                "prices_include_vat": False, "vat_percent": 20.0})  # fmt: skip
    assert price_cent(awattar, at("2026-06-20 13:00"), ctx_plain, epex_cent=5.0) == 7.98
    assert price_cent(vkw, at("2026-06-20 13:00"), ctx_plain, epex_cent=10.0) == 13.44
