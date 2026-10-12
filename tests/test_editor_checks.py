"""Editor checks: plausibility, preview curves, invoice check."""

from datetime import date

import pytest
from conftest import at, load_example, make

from edbert.editor.invoice import BASE_BAND, invoice_bands, invoice_check
from edbert.editor.plausibility import analyze_rules, plausibility_warnings
from edbert.editor.preview import (
    day_curve,
    example_market_profile,
    representative_dates,
)
from edbert.errors import EdbertError, ErrorCode, WarningCode
from edbert.gridfee import parse_grid_fee_config, resolve_grid_fee

BASE = {"id": "t", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0}
ALL_DAY = {"id": "all", "effect": {"mode": "add_cent", "value": 1.0}}
NIGHT = {"id": "night", "time": {"from": "22:00", "to": "06:00"}, "effect": {"mode": "absolute_cent", "value": 20.0}}


def codes(warnings):
    return [(w.code, dict(w.params)) for w in warnings]


def test_good_example_has_no_plausibility_warning(ctx_de):
    tariff = make(load_example("fixed_day_night.json"))
    assert plausibility_warnings(tariff, ctx_de, 2026) == []


def test_rule_hidden_behind_an_earlier_rule_is_reported(ctx_plain):
    tariff = make(BASE, rules=[ALL_DAY, NIGHT])
    assert codes(plausibility_warnings(tariff, ctx_plain, 2026)) == [
        (WarningCode.RULE_SHADOWED, {"rule_id": "night", "by": "all"})
    ]
    reversed_order = make(BASE, rules=[NIGHT, ALL_DAY])
    assert plausibility_warnings(reversed_order, ctx_plain, 2026) == []  # the all-day rule still wins by day


def test_rule_that_can_never_match_is_reported(ctx_plain):
    expired = {**NIGHT, "id": "old", "valid_to": "2020-12-31"}
    tariff = make(BASE, rules=[expired])
    assert [w.code for w in plausibility_warnings(tariff, ctx_plain, 2026)] == [WarningCode.RULE_NEVER_APPLIES]


def test_analysis_counts_wins_and_candidates(ctx_plain):
    stats = analyze_rules(make(BASE, rules=[NIGHT]), ctx_plain, 2026)["night"]
    assert stats.candidates == stats.wins == 730 * 32  # 8 hours = 32 slots a day, 2026 and 2027


def test_analysis_without_a_region_ignores_holidays_instead_of_failing(ctx_plain):
    weekend = {"id": "we", "weekdays": "weekend", "effect": {"mode": "add_cent", "value": 1}}
    assert analyze_rules(make(BASE, rules=[weekend]), ctx_plain, 2026)["we"].wins > 0


def test_unusual_prices_are_flagged(ctx_plain):
    assert [w.code for w in plausibility_warnings(make(BASE, fix_cent_kwh=0.32), ctx_plain, 2026)] == [WarningCode.PRICE_UNUSUAL]
    assert [w.code for w in plausibility_warnings(make(BASE, fix_cent_kwh=92.0), ctx_plain, 2026)] == [WarningCode.PRICE_UNUSUAL]
    spot_gross = make({"id": "s", "type": "spot_hourly", "supplier_id": "x", "prices_include_vat": True})
    assert [w.code for w in plausibility_warnings(spot_gross, ctx_plain, 2026)] == [WarningCode.SPOT_PRICES_GROSS]


def test_representative_days(ctx_de):
    tariff = make(load_example("fixed_day_night.json"))
    days = representative_dates(ctx_de, tariff, 2026, 12)
    assert days == {"weekday": date(2026, 12, 2), "saturday": date(2026, 12, 5), "sunday": date(2026, 12, 6), "holiday": date(2026, 12, 25)}
    without_region = representative_dates(ctx_de.__class__("Europe/Berlin"), tariff, 2026, 12)
    assert "holiday" not in without_region


def test_day_curves_for_fixed_and_spot_tariffs(ctx_de):
    fixed = make(load_example("fixed_day_night.json"))
    curve = day_curve(fixed, ctx_de, date(2026, 12, 2))
    assert len(curve) == 96
    assert (curve[0].cent, curve[48].cent) == (25.0, 32.0)
    assert day_curve(fixed, ctx_de, date(2026, 12, 25))[48].cent == 27.0  # holiday counts as Sunday

    spot = make(load_example("spot_evening_surcharge_cap.json"))
    spot_curve = day_curve(spot, ctx_de, date(2026, 7, 15))
    profile = example_market_profile()
    assert len(profile) == 96
    assert spot_curve[48].supplier_cent == pytest.approx(profile[48] * 1.03 + 1.5)


def test_day_curve_on_daylight_saving_days(ctx_plain):
    fixed = make(BASE)
    assert len(day_curve(fixed, ctx_plain, date(2026, 3, 29))) == 92
    spot = make({"id": "s", "type": "spot_hourly", "supplier_id": "x"})
    assert len(day_curve(spot, ctx_plain, date(2026, 10, 25))) == 100  # the profile is reused for the repeated hour


def test_invoice_check_of_a_fixed_tariff(ctx_de):
    tariff = make(load_example("fixed_day_night.json"), monthly_fee_eur=12.9)
    bands = {band.id: band.cent for band in invoice_bands(tariff, ctx_de, date(2026, 10, 1))}
    assert bands == {BASE_BAND: 32.0, "night": 25.0, "weekend": 27.0}
    kwh = {BASE_BAND: 100.0, "night": 50.0, "weekend": 20.0}
    exact = invoice_check(tariff, ctx_de, date(2026, 10, 1), kwh, 62.80)
    assert (exact.energy_eur, exact.fees_eur, exact.expected_eur) == (49.9, 12.9, 62.8)
    assert exact.ok
    assert exact.deviation_percent == 0.0
    wrong = invoice_check(tariff, ctx_de, date(2026, 10, 1), kwh, 70.0)
    assert not wrong.ok
    assert wrong.deviation_percent == pytest.approx(-10.29, abs=0.01)


def test_invoice_fees_get_vat_when_prices_are_net(ctx_plain):
    tariff = make({**BASE, "prices_include_vat": False, "vat_percent": 20, "monthly_fee_eur": 5.0})
    result = invoice_check(tariff, ctx_plain, date(2026, 10, 1), {BASE_BAND: 100.0}, 42.0)
    assert result.fees_eur == 6.0
    assert result.energy_eur == 36.0
    assert result.ok


def test_invoice_check_rejects_unknown_bands_and_exports(ctx_plain):
    tariff = make(BASE)
    month = date(2026, 10, 1)
    with pytest.raises(EdbertError) as err:
        invoice_check(tariff, ctx_plain, month, {"night": 10.0}, 10.0)
    assert err.value.code == ErrorCode.VALUE_INVALID
    export = make({"id": "e", "type": "fixed", "supplier_id": "s", "k_push_cent": 5.0}, direction="export")
    with pytest.raises(EdbertError):
        invoice_check(export, ctx_plain, month, {BASE_BAND: 1.0}, 10.0)


def test_invoice_bands_of_a_spot_tariff_need_the_month_average(ctx_plain):
    spot = make({"id": "s", "type": "spot_hourly", "supplier_id": "x", "settlement_fee_cent_kwh": 1.5})
    month = date(2026, 10, 1)
    with pytest.raises(EdbertError) as err:
        invoice_bands(spot, ctx_plain, month)
    assert err.value.code == ErrorCode.MARKET_PRICE_REQUIRED
    assert invoice_bands(spot, ctx_plain, month, market_cent=10.0)[0].cent == 11.5


def test_invoice_with_grid_fee(ctx_plain):
    fee = resolve_grid_fee(parse_grid_fee_config({"base_cent_kwh": 8.0}))
    result = invoice_check(make(BASE), ctx_plain, date(2026, 10, 1), {BASE_BAND: 100.0}, 38.0, grid_fee=fee)
    assert result.energy_eur == 38.0
    assert result.ok
    assert at("2026-10-01 00:00")  # helper import kept in use
