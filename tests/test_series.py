"""Price series: horizon, resolution, DST days, hourly settlement, components, quality, warnings."""

import json
from datetime import timedelta

import pytest
from conftest import at, flat_grid_fee, load_example, make

from edibert.checks import check_grid_fee, check_tariff
from edibert.errors import EdibertError, ErrorCode, WarningCode
from edibert.gridfee import parse_grid_fee_config, resolve_grid_fee
from edibert.i18n import Translator
from edibert.series import QUALITY_EXACT, QUALITY_FORECAST, tariff_price_series

FIXED_NIGHT = {
    "id": "f", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0, "vat_percent": 20,
    "rules": [{"id": "night", "time": {"from": "22:00", "to": "06:00"},
               "effect": {"mode": "absolute_cent", "value": 20.0}}],
}  # fmt: skip
SPOT = {"id": "sp", "type": "spot_hourly", "supplier_id": "s", "prices_include_vat": False, "vat_percent": 20}


def code_of(func, *args, **kwargs):
    with pytest.raises(EdibertError) as err:
        func(*args, **kwargs)
    return err.value.code


def market_for_day(day: str, ctx, values):
    """15-minute market prices from midnight, ``values`` cycling."""
    start = ctx.to_local(at(f"{day} 00:00"))
    return {start + timedelta(minutes=15 * i): values[i % len(values)] for i in range(96)}


def test_day_resolutions(ctx_plain):
    tariff = make(FIXED_NIGHT)
    for resolution, expected in ((15, 96), (30, 48), (60, 24)):
        series = tariff_price_series(
            tariff, ctx_plain, at("2026-10-12 00:00"), at("2026-10-13 00:00"), resolution_min=resolution
        )
        assert len(series.points) == expected
    hourly = tariff_price_series(tariff, ctx_plain, at("2026-10-12 00:00"), at("2026-10-13 00:00"), resolution_min=60)
    assert [p.cent for p in hourly.points][:7] == [20.0] * 6 + [30.0]
    assert hourly.points[22].cent == 20.0


def test_dst_days_have_23_and_25_hours(ctx_plain):
    tariff = make(FIXED_NIGHT)
    spring = tariff_price_series(tariff, ctx_plain, at("2026-03-29 00:00"), at("2026-03-30 00:00"), resolution_min=15)
    autumn = tariff_price_series(tariff, ctx_plain, at("2026-10-25 00:00"), at("2026-10-26 00:00"), resolution_min=60)
    assert len(spring.points) == 92
    assert len(autumn.points) == 25
    assert spring.points[0].start.utcoffset() != spring.points[-1].start.utcoffset()


def test_points_are_contiguous_and_carry_the_local_offset(ctx_plain):
    series = tariff_price_series(make(FIXED_NIGHT), ctx_plain, at("2026-10-25 00:00"), at("2026-10-26 00:00"), resolution_min=60)
    for first, second in zip(series.points, series.points[1:], strict=False):
        assert first.end == second.start
    assert series.points[0].start.isoformat().endswith("+02:00")
    assert series.points[-1].end.isoformat().endswith("+01:00")


@pytest.mark.parametrize(
    ("start", "end", "resolution"),
    [("2026-10-12 00:10", "2026-10-13 00:00", 15), ("2026-10-12 00:15", "2026-10-13 00:00", 60), ("2026-10-12 00:00", "2026-10-12 00:20", 15), ("2026-10-13 00:00", "2026-10-12 00:00", 15)],
)  # fmt: skip
def test_misaligned_or_empty_ranges_are_errors(ctx_plain, start, end, resolution):
    assert code_of(tariff_price_series, make(FIXED_NIGHT), ctx_plain, at(start), at(end), resolution_min=resolution) == ErrorCode.VALUE_INVALID


def test_unknown_resolution_is_an_error(ctx_plain):
    assert code_of(tariff_price_series, make(FIXED_NIGHT), ctx_plain, at("2026-10-12 00:00"), at("2026-10-13 00:00"), resolution_min=20) == ErrorCode.VALUE_INVALID


def test_spot_series_uses_the_market_price_per_quarter_hour(ctx_plain):
    tariff = make(SPOT)
    market = market_for_day("2026-10-12", ctx_plain, [10.0, 20.0])
    series = tariff_price_series(tariff, ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 01:00"), market=market)
    assert [p.supplier_cent for p in series.points] == [10.0, 20.0, 10.0, 20.0]
    assert [p.cent for p in series.points] == [12.0, 24.0, 12.0, 24.0]  # incl. 20 % VAT


def test_hourly_resolution_averages_and_hourly_settlement_uses_the_hour_mean(ctx_plain):
    market = market_for_day("2026-10-12", ctx_plain, [10.0, 12.0, 14.0, 16.0])
    quarter_settled = make(SPOT)
    hour_settled = make(SPOT, settlement_mtu="60min")
    for tariff in (quarter_settled, hour_settled):
        hourly = tariff_price_series(tariff, ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 01:00"), resolution_min=60, market=market)
        assert hourly.points[0].supplier_cent == 13.0
    quarters = tariff_price_series(hour_settled, ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 01:00"), market=market)
    assert {p.supplier_cent for p in quarters.points} == {13.0}  # every slot of the hour has the hour price


def test_missing_market_price_is_an_error_not_a_guess(ctx_plain):
    market = market_for_day("2026-10-12", ctx_plain, [10.0])
    del market[next(iter(market))]
    assert code_of(tariff_price_series, make(SPOT), ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 01:00"), market=market) == ErrorCode.PRICE_MISSING
    hour = make(SPOT, settlement_mtu="60min")  # one missing slot spoils the hour mean
    assert code_of(tariff_price_series, hour, ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 01:00"), market=market) == ErrorCode.PRICE_MISSING


def test_fixed_tariff_needs_no_market(ctx_plain):
    series = tariff_price_series(make(FIXED_NIGHT), ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 02:00"), market=None)
    assert all(p.quality == QUALITY_EXACT for p in series.points)


def test_forecast_quality_from_a_given_time(ctx_plain):
    market = market_for_day("2026-10-12", ctx_plain, [10.0])
    series = tariff_price_series(
        make(SPOT), ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 04:00"), resolution_min=60,
        market=market, forecast_from=at("2026-10-12 02:30"),
    )  # fmt: skip
    assert [p.quality for p in series.points] == [QUALITY_EXACT, QUALITY_EXACT, QUALITY_FORECAST, QUALITY_FORECAST]
    fixed = tariff_price_series(make(FIXED_NIGHT), ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 04:00"), forecast_from=at("2026-10-12 01:00"))
    assert {p.quality for p in fixed.points} == {QUALITY_EXACT}  # a fixed price is never a forecast


def test_components_add_up_with_grid_fee_and_vat(ctx_plain):
    fee = flat_grid_fee(8.0)
    market = market_for_day("2026-10-12", ctx_plain, [10.0])
    series = tariff_price_series(make(SPOT), ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 02:00"), resolution_min=60, market=market, grid_fee=fee)
    point = series.points[0]
    assert (point.supplier_cent, point.grid_cent, point.cent) == (10.0, 8.0, 21.6)
    assert point.vat_cent == 3.6
    assert point.supplier_cent + point.grid_cent + point.vat_cent == pytest.approx(point.cent)


def test_series_is_json_serializable(ctx_plain):
    series = tariff_price_series(make(FIXED_NIGHT), ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 01:00"))
    data = json.loads(json.dumps(series.to_dict()))
    assert data["tariff_id"] == "f"
    assert data["unit"] == "cent/kWh"
    assert data["points"][0]["start"].startswith("2026-10-12T00:00:00")


def test_export_series_with_negative_price_rule(ctx_de):
    tariff = make(load_example("export_no_pay_at_negative_price.json"), direction="export")
    market = {ctx_de.to_local(at("2026-06-20 12:00")): -3.0, ctx_de.to_local(at("2026-06-20 12:15")): 4.0}
    series = tariff_price_series(tariff, ctx_de, at("2026-06-20 12:00"), at("2026-06-20 12:30"), market=market)
    assert [p.cent for p in series.points] == [0.0, 7.8]


def test_warning_for_windows_not_on_the_hour_in_hourly_tariffs():
    rules = [{"id": "ht", "time": {"from": "17:15", "to": "19:00"}, "effect": {"mode": "add_cent", "value": 1}}]
    hourly = make(SPOT, settlement_mtu="60min", rules=rules)
    assert [w.code for w in check_tariff(hourly)] == [WarningCode.WINDOW_NOT_HOUR_ALIGNED]
    assert check_tariff(make(SPOT, rules=rules)) == []  # quarter-hour settlement is fine


def test_requirement_warning_is_translated():
    tariff = make(FIXED_NIGHT, requires=["smart_meter"])
    warnings = check_tariff(tariff, capabilities={"quarter_hour_meter"})
    assert [w.params["requirement"] for w in warnings] == ["smart_meter"]
    assert "Smart Meter" in Translator("de").warning(warnings[0])
    assert "smart meter" in Translator("en").warning(warnings[0])
    assert check_tariff(tariff, capabilities={"smart_meter"}) == []


def test_series_collects_warnings_from_tariff_and_grid_fee(ctx_plain):
    catalog = {"tariff_format": 1, "rule_sets": {"S": [{"id": "snap", "status": "verordnet", "requires": ["quarter_hour_meter"],
                                    "effect": {"mode": "percent_off", "value": 20}}]},
               "areas": [{"id": "A", "base_cent_kwh": {"unmetered_power": 5, "metered_power": 3}, "rule_set": "S"}]}  # fmt: skip
    from edibert.gridfee import parse_grid_fee_catalog

    fee = resolve_grid_fee(parse_grid_fee_config({"area_id": "A"}), parse_grid_fee_catalog(catalog))
    assert [w.code for w in check_grid_fee(fee)] == [WarningCode.GRID_RULE_SKIPPED_NO_QUARTER_HOUR_METER]
    series = tariff_price_series(make(FIXED_NIGHT, requires=["smart_meter"]), ctx_plain, at("2026-10-12 00:00"), at("2026-10-12 01:00"), grid_fee=fee, capabilities=set())
    assert {w.code for w in series.warnings} == {WarningCode.REQUIREMENT_UNMET, WarningCode.GRID_RULE_SKIPPED_NO_QUARTER_HOUR_METER}
