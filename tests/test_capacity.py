"""Capacity charge (section 5b): loading, month amount, ladder, price-series block and CLI."""

import copy
import json
from datetime import date, datetime

import pytest
from conftest import EXAMPLES, at, load_example, make

from edibert.capacity import (
    CapacityState,
    capacity_charge_eur,
    capacity_ladder,
    charge_for_month,
    parse_capacity_state,
)
from edibert.checks import check_grid_fee
from edibert.cli import main
from edibert.errors import EdibertError, ErrorCode, WarningCode
from edibert.gridfee import (
    CATALOG,
    USER,
    parse_grid_fee_catalog,
    parse_grid_fee_config,
    resolve_grid_fee,
)
from edibert.series import tariff_price_series

FIXED = {"id": "user_fixed", "label": "Fixed", "type": "fixed_cent", "fix_cent_kwh": 20.0, "supplier_id": "user_test",
         "prices_include_vat": True, "vat_percent": 20}
CHARGE = {
    "id": "lp_2027",
    "basis": "monthly_peak_15min",
    "min_kw": 2.0,
    "bands": [{"up_to_kw": 10, "cent_per_kw_month": 150}, {"up_to_kw": None, "cent_per_kw_month": 300}],
    "valid_from": "2027-01-01",
    "valid_to": "2027-12-31",
}


def document(*charges: dict, area_id: str = "user_home") -> dict:
    area = {"id": area_id, "base_cent_kwh": {"unmetered_power": 4.5, "metered_power": 4.5}}
    area["capacity_charges"] = [copy.deepcopy(charge) for charge in charges]
    return {"tariff_format": 1, "areas": [area]}


def grid_fee(*charges: dict, **config):
    return resolve_grid_fee(
        parse_grid_fee_config({"area_id": "user_home", "quarter_hour_meter": True, **config}),
        parse_grid_fee_catalog(document(*charges), USER),
    )


def charge(**changes):
    return grid_fee({**CHARGE, **changes}).capacity[0]


def code_of(func, *args, **kwargs):
    with pytest.raises(EdibertError) as err:
        func(*args, **kwargs)
    return err.value.code


def test_example_file_loads_and_prices(ctx_plain):
    config = parse_grid_fee_config({"area_id": "user_capacity_example", "include_status": ["entwurf"]})
    fee = resolve_grid_fee(config, parse_grid_fee_catalog(load_example("grid_fee_capacity_example.json"), USER))
    assert capacity_charge_eur(fee.capacity[0], 12.0) == 21.0  # 10 * 1.50 + 2 * 3.00


@pytest.mark.parametrize(
    ("peak", "amount"),
    [(0.0, 3.0), (1.5, 3.0), (2.0, 3.0), (6.0, 9.0), (10.0, 15.0), (12.5, 22.5)],
)
def test_month_amount_applies_minimum_and_bands(peak, amount):
    assert capacity_charge_eur(charge(), peak) == amount


def test_month_amount_is_rounded_to_cents():
    assert capacity_charge_eur(charge(), 3.333) == 5.0  # 3.333 * 1.50 = 4.9995


def test_negative_peak_is_rejected():
    assert code_of(capacity_charge_eur, charge(), -1.0) == ErrorCode.VALUE_INVALID


@pytest.mark.parametrize(
    "changes",
    [
        {"basis": "monthly_peak_60min"},
        {"min_kw": -1},
        {"bands": []},
        {"bands": [{"up_to_kw": 10, "cent_per_kw_month": 150}]},  # last band must be open-ended
        {"bands": [{"up_to_kw": None, "cent_per_kw_month": 150}, {"up_to_kw": None, "cent_per_kw_month": 300}]},
        {"bands": [{"up_to_kw": 10, "cent_per_kw_month": 150}, {"up_to_kw": 8, "cent_per_kw_month": 300},
                   {"up_to_kw": None, "cent_per_kw_month": 300}]},
        {"bands": [{"up_to_kw": None, "cent_per_kw_month": -1}]},
        {"valid_from": "2027-01-15"},  # a charge covers whole months
        {"valid_to": "2027-12-30"},
        {"valid_from": "2027-06-01", "valid_to": "2027-05-31"},
        {"status": "gilt"},
    ],
)
def test_invalid_charges_are_rejected(changes):
    assert code_of(grid_fee, {**CHARGE, **changes}) == ErrorCode.VALUE_INVALID


@pytest.mark.parametrize("field", ["id", "basis", "min_kw", "bands"])
def test_required_charge_fields(field):
    raw = {key: value for key, value in CHARGE.items() if key != field}
    assert code_of(grid_fee, raw) == ErrorCode.FIELD_MISSING


def test_band_needs_explicit_upper_limit_and_rate():
    assert code_of(grid_fee, {**CHARGE, "bands": [{"cent_per_kw_month": 150}]}) == ErrorCode.FIELD_MISSING
    assert code_of(grid_fee, {**CHARGE, "bands": [{"up_to_kw": None}]}) == ErrorCode.FIELD_MISSING


def test_unknown_fields_are_rejected():
    assert code_of(grid_fee, {**CHARGE, "min_percent_of_contracted": 20}) == ErrorCode.TARIFF_UNKNOWN_FIELD
    assert code_of(grid_fee, {**CHARGE, "eur_per_kw_year": 19}) == ErrorCode.TARIFF_UNKNOWN_FIELD
    bands = [{"up_to_kw": None, "eur_per_kw_year": 19}]
    assert code_of(grid_fee, {**CHARGE, "bands": bands}) == ErrorCode.TARIFF_UNKNOWN_FIELD


def test_overlapping_and_duplicate_entries_are_rejected():
    later = {**CHARGE, "id": "lp_2028", "valid_from": "2027-12-01", "valid_to": None}
    assert code_of(grid_fee, CHARGE, later) == ErrorCode.VALUE_INVALID
    assert code_of(grid_fee, CHARGE, {**CHARGE, "valid_from": "2028-01-01", "valid_to": None}) == ErrorCode.VALUE_INVALID


def test_catalog_charges_need_a_status():
    doc = document(CHARGE, area_id="AT-TEST")
    assert code_of(parse_grid_fee_catalog, doc, CATALOG) == ErrorCode.FIELD_MISSING
    doc["areas"][0]["capacity_charges"][0]["status"] = "entwurf"
    assert parse_grid_fee_catalog(doc, CATALOG).areas["AT-TEST"].capacity_charges[0].status == "entwurf"


def test_status_filter_skips_with_warning():
    fee = grid_fee({**CHARGE, "status": "entwurf"})
    assert fee.capacity == ()
    warnings = check_grid_fee(fee)
    assert [(item.code, item.params) for item in warnings] == [
        (WarningCode.GRID_CAPACITY_SKIPPED_STATUS, {"charge_id": "lp_2027", "status": "entwurf"})
    ]
    assert grid_fee({**CHARGE, "status": "entwurf"}, include_status=["verordnet", "entwurf"]).capacity


def test_no_quarter_hour_meter_keeps_the_charge_and_warns():
    fee = grid_fee(CHARGE, quarter_hour_meter=False)
    assert fee.capacity
    assert [item.code for item in check_grid_fee(fee)] == [WarningCode.CAPACITY_STATE_UNAVAILABLE]


def test_non_convex_bands_warn():
    bands = [{"up_to_kw": 10, "cent_per_kw_month": 300}, {"up_to_kw": None, "cent_per_kw_month": 150}]
    fee = grid_fee({**CHARGE, "bands": bands})
    assert [item.code for item in check_grid_fee(fee)] == [WarningCode.CAPACITY_BANDS_NOT_CONVEX]


def test_charge_for_month_before_start_gap_and_after_end():
    first = {**CHARGE, "valid_to": "2027-06-30"}
    second = {**CHARGE, "id": "lp_b", "valid_from": "2027-09-01", "valid_to": "2027-12-31"}
    fee = grid_fee(first, second)
    assert charge_for_month(fee.capacity, date(2026, 12, 5), "user_home") is None  # not introduced yet
    assert charge_for_month(fee.capacity, date(2027, 3, 1), "user_home").id == "lp_2027"
    assert charge_for_month(fee.capacity, date(2027, 10, 31), "user_home").id == "lp_b"
    for month in (date(2027, 7, 1), date(2028, 1, 1)):  # gap, outdated list
        with pytest.raises(EdibertError) as err:
            charge_for_month(fee.capacity, month, "user_home")
        assert err.value.code == ErrorCode.CAPACITY_CHARGE_MISSING
        assert err.value.params == {"area_id": "user_home", "month": month.strftime("%Y-%m")}


def test_open_ended_charge_covers_every_later_month():
    fee = grid_fee({**CHARGE, "valid_to": None})
    assert charge_for_month(fee.capacity, date(2031, 5, 1), "user_home").id == "lp_2027"


def rungs(ladder):
    return [(rung.up_to_kw, rung.extra_eur, rung.marginal_eur_per_kw, rung.reached) for rung in ladder.rungs]


def test_relative_ladder_from_state(ctx_plain):
    state = CapacityState(4.0, at("2027-01-14 18:00"))
    ladder = capacity_ladder(charge(), state, date(2027, 1, 1), ctx_plain)
    assert ladder.free_up_to_kw == 4.0
    assert rungs(ladder) == [
        (0.0, 0.0, 0.0, True),
        (2.0, 0.0, 0.0, True),
        (4.0, 0.0, 1.5, True),
        (10.0, 9.0, 3.0, False),
    ]


def test_state_below_minimum_frees_up_to_minimum(ctx_plain):
    ladder = capacity_ladder(charge(), CapacityState(1.0, at("2027-01-02 08:00")), date(2027, 1, 1), ctx_plain)
    assert ladder.free_up_to_kw == 2.0
    assert rungs(ladder)[1:3] == [(1.0, 0.0, 0.0, True), (2.0, 0.0, 1.5, True)]


def test_absolute_ladder_without_state(ctx_plain):
    ladder = capacity_ladder(charge(), None, date(2027, 1, 1), ctx_plain)
    assert ladder.state is None
    assert rungs(ladder) == [(0.0, 3.0, 0.0, False), (2.0, 3.0, 1.5, False), (10.0, 15.0, 3.0, False)]
    assert code_of(capacity_ladder, charge(), None, date(2027, 1, 1), ctx_plain, require_state=True) == (
        ErrorCode.CAPACITY_STATE_MISSING
    )


def test_ladder_steps(ctx_plain):
    ladder = capacity_ladder(charge(), None, date(2027, 1, 1), ctx_plain, step_kw=4, max_kw=13)
    assert [rung.up_to_kw for rung in ladder.rungs] == [0.0, 2.0, 4.0, 8.0, 10.0, 12.0, 13.0]
    assert code_of(capacity_ladder, charge(), None, date(2027, 1, 1), ctx_plain, step_kw=4) == ErrorCode.FIELD_MISSING
    assert code_of(capacity_ladder, charge(), None, date(2027, 1, 1), ctx_plain, step_kw=0, max_kw=4) == (
        ErrorCode.VALUE_INVALID
    )


def test_state_month_is_local_time(ctx_plain):
    state = CapacityState(5.0, datetime.fromisoformat("2027-01-31T23:30:00+00:00"))  # 00:30 on 1 Feb in Vienna
    with pytest.raises(EdibertError) as err:
        capacity_ladder(charge(), state, date(2027, 1, 1), ctx_plain)
    assert err.value.code == ErrorCode.CAPACITY_STATE_MONTH_MISMATCH
    assert err.value.params == {"month": "2027-01", "state_month": "2027-02"}
    assert capacity_ladder(charge(), state, date(2027, 2, 1), ctx_plain).free_up_to_kw == 5.0


def test_parse_capacity_state():
    state = parse_capacity_state({"peak_15min_kw": 3.5, "as_of": "2027-01-14T18:00"})
    assert state == CapacityState(3.5, datetime(2027, 1, 14, 18, 0))
    assert code_of(parse_capacity_state, {"as_of": "2027-01-14T18:00"}) == ErrorCode.FIELD_MISSING
    assert code_of(parse_capacity_state, {"peak_15min_kw": -1, "as_of": "2027-01-14"}) == ErrorCode.VALUE_INVALID
    assert code_of(parse_capacity_state, {"peak_15min_kw": 1, "as_of": "today"}) == ErrorCode.VALUE_INVALID


def test_series_carries_a_capacity_block_per_month(ctx_plain):
    fee = grid_fee({**CHARGE, "valid_from": "2027-01-01", "valid_to": None})
    state = CapacityState(4.0, at("2027-01-31 12:00"))
    series = tariff_price_series(
        make(FIXED), ctx_plain, at("2026-12-31 00:00"), at("2027-02-01 12:00"), resolution_min=60,
        grid_fee=fee, capacity_state=state,
    )  # fmt: skip
    without = tariff_price_series(
        make(FIXED), ctx_plain, at("2026-12-31 00:00"), at("2027-02-01 12:00"), resolution_min=60, grid_fee=fee
    )
    assert [point.cent for point in series.points] == [point.cent for point in without.points]
    block = series.to_dict()["capacity"]
    assert [entry["month"] for entry in block] == ["2027-01", "2027-02"]  # December 2026: not introduced yet
    january, february = block
    assert january["state"] == {"peak_15min_kw": 4.0, "as_of": "2027-01-31T12:00:00"}
    assert january["free_up_to_kw"] == 4.0
    assert january["days_remaining"] == 31  # the range starts before January, so the whole month counts
    assert january["unit"] == "EUR once per month, net"
    assert february["state"] == {"peak_15min_kw": 0.0, "as_of": None}
    assert february["free_up_to_kw"] == 2.0
    assert february["days_remaining"] == 28
    assert [rung["reached"] for rung in february["ladder"]] == [True, True, False]
    assert without.to_dict()["capacity"][0]["state"] is None


def test_series_days_remaining_count_from_range_start(ctx_plain):
    series = tariff_price_series(
        make(FIXED), ctx_plain, at("2027-01-14 18:00"), at("2027-01-15 18:00"), grid_fee=grid_fee(CHARGE),
        capacity_state=CapacityState(3.0, at("2027-01-14 18:00")),
    )  # fmt: skip
    assert series.to_dict()["capacity"][0]["days_remaining"] == 18


def test_series_without_capacity_charge_has_no_block(ctx_plain):
    series = tariff_price_series(make(FIXED), ctx_plain, at("2027-01-01 00:00"), at("2027-01-01 01:00"))
    assert "capacity" not in series.to_dict()
    feed_in = {"id": "user_feed", "label": "Feed-in", "type": "fixed", "k_push_cent": 7.0, "supplier_id": "user_test",
               "prices_include_vat": True, "vat_percent": 0}  # fmt: skip
    export = make(feed_in, direction="export")
    series = tariff_price_series(export, ctx_plain, at("2027-01-01 00:00"), at("2027-01-01 01:00"), grid_fee=grid_fee(CHARGE))
    assert "capacity" not in series.to_dict()


def test_series_month_before_the_state_month_is_absolute(ctx_plain):
    series = tariff_price_series(
        make(FIXED), ctx_plain, at("2027-01-01 00:00"), at("2027-01-01 01:00"),
        grid_fee=grid_fee(CHARGE), capacity_state=CapacityState(3.0, at("2027-03-01 00:00")),
    )  # fmt: skip
    january = series.to_dict()["capacity"][0]
    assert january["state"] is None
    assert january["ladder"][0]["extra_eur"] == 3.0


def run_cli(capsys, tmp_path, *argv):
    config = tmp_path / "netznutzung.json"
    config.write_text(json.dumps({"area_id": "user_capacity_example", "include_status": ["entwurf"]}), encoding="utf-8")
    code = main(["capacity", "--grid-fee", str(config), "--user-grid-fees", str(EXAMPLES / "grid_fee_capacity_example.json"),
                 "--tz", "Europe/Vienna", *argv])  # fmt: skip
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_capacity_table(capsys, tmp_path):
    code, out, _ = run_cli(capsys, tmp_path, "--month", "2027-01", "--peak-so-far", "4", "--as-of", "2027-01-14T18:00",
                           "--power", "12")  # fmt: skip
    assert code == 0
    assert "no extra cost up to 4.00 kW" in out
    assert "Month amount at a peak of 12.00 kW: 21.00 EUR (net)" in out
    assert "10.00 kW  +9.00 EUR  then 3.00 EUR/kW" in out
    assert "4.00 kW  +0.00 EUR  then 1.50 EUR/kW  [reached]" in out


def test_cli_capacity_json_and_errors(capsys, tmp_path):
    code, out, _ = run_cli(capsys, tmp_path, "--month", "2027-02", "--format", "json", "--step", "5", "--max", "15")
    assert code == 0
    result = json.loads(out)
    assert result["state"] is None
    assert [rung["up_to_kw"] for rung in result["ladder"]] == [0.0, 2.0, 5.0, 10.0, 15.0]
    code, _, err = run_cli(capsys, tmp_path, "--month", "2027-02", "--peak-so-far", "4")
    assert code == 2 and "--as-of" in err
    code, _, err = run_cli(capsys, tmp_path, "--month", "2028-01")
    assert code == 2 and "covers 2028-01" in err
    code, out, _ = run_cli(capsys, tmp_path, "--month", "2026-12")
    assert code == 0 and "has no capacity charge in 2026-12" in out
