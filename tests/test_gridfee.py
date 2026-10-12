"""Grid fee: own rules (section 14a module 3 shape), Earnie-shaped catalog, status and meter handling."""

import pytest
from conftest import at, load_example, make

from edbert.errors import EdbertError, ErrorCode
from edbert.gridfee import (
    SKIP_NO_QUARTER_HOUR_METER,
    SKIP_STATUS,
    load_grid_fee_config,
    parse_grid_fee_catalog,
    parse_grid_fee_config,
    resolve_grid_fee,
)
from edbert.tariff import evaluate, price_cent

CATALOG = {
    "description": "test catalog (Earnie shape)",
    "rule_sets": {
        "AT_NE7": [
            {"id": "SNAP", "label": "Summer low", "status": "verordnet", "valid_from": "2026-04-01",
             "months": [4, 5, 6, 7, 8, 9], "time": {"from": "10:00", "to": "16:00"}, "weekdays": None,
             "effect": {"mode": "percent_off", "value": 20.0}, "requires": ["quarter_hour_meter"]},
            {"id": "WiNAP", "status": "entwurf", "valid_from": "2027-01-01",
             "months": [10, 11, 12, 1, 2, 3], "time": {"from": "22:00", "to": "04:00"},
             "effect": {"mode": "percent_off", "value": None}, "requires": ["quarter_hour_meter"]},
        ]
    },
    "areas": [
        {"id": "AT-VBG", "label": "Vorarlberg", "land": "AT", "rule_set": "AT_NE7",
         "base_cent_kwh": {"unmetered_power": 7.0, "metered_power": 4.0}, "source": "test"},
        {"id": "AT-PLAIN", "label": "No rules", "base_cent_kwh": {"unmetered_power": 5.0, "metered_power": 3.0}},
    ],
}  # fmt: skip

FIXED = {"id": "t", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 20.0}


def code_of(func, *args, **kwargs):
    with pytest.raises(EdbertError) as err:
        func(*args, **kwargs)
    return err.value.code


def test_modul3_example_levels(ctx_de):
    config = parse_grid_fee_config(load_example("grid_fee_modul3_example.json")["netznutzung"])
    fee = resolve_grid_fee(config)
    assert fee.work_cent(ctx_de.to_local(at("2026-10-12 03:00")), ctx_de) == (1.0, "nt")
    assert fee.work_cent(ctx_de.to_local(at("2026-10-12 12:00")), ctx_de) == (9.98, None)
    assert fee.work_cent(ctx_de.to_local(at("2026-10-12 16:00")), ctx_de) == (14.92, "ht")
    assert fee.work_cent(ctx_de.to_local(at("2026-10-12 20:00")), ctx_de) == (9.98, None)  # end exclusive


def test_example_file_loader_accepts_wrapper_and_bare_object(tmp_path):
    import json

    wrapped = load_grid_fee_config(__import__("conftest").EXAMPLES / "grid_fee_modul3_example.json")
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps(load_example("grid_fee_modul3_example.json")["netznutzung"]), encoding="utf-8")
    assert load_grid_fee_config(bare) == wrapped


def test_grid_fee_is_added_before_vat(ctx_plain):
    spot = make({"id": "s", "type": "spot_hourly", "supplier_id": "x", "settlement_fee_cent_kwh": 1.0,
                 "prices_include_vat": False, "vat_percent": 20.0})  # fmt: skip
    fee = resolve_grid_fee(parse_grid_fee_config({"base_cent_kwh": 8.0}))
    result = evaluate(spot, at("2026-10-12 12:00"), ctx_plain, epex_cent=10.0, grid_fee=fee)
    assert result.after_limits_cent == 11.0
    assert result.grid_cent == 8.0
    assert result.cent == pytest.approx((11.0 + 8.0) * 1.2)


def test_grid_fee_is_not_applied_to_export(ctx_plain):
    export = make({"id": "e", "type": "fixed", "supplier_id": "s", "k_push_cent": 5.0}, direction="export")
    fee = resolve_grid_fee(parse_grid_fee_config({"base_cent_kwh": 8.0}))
    assert price_cent(export, at("2026-10-12 12:00"), ctx_plain, grid_fee=fee) == 5.0


def test_catalog_area_snap_needs_quarter_hour_meter(ctx_at):
    catalog = parse_grid_fee_catalog(CATALOG)
    with_meter = resolve_grid_fee(parse_grid_fee_config({"area_id": "AT-VBG", "quarter_hour_meter": True}), catalog)
    without = resolve_grid_fee(parse_grid_fee_config({"area_id": "AT-VBG"}), catalog)
    noon = ctx_at.to_local(at("2026-07-15 12:00"))
    assert with_meter.work_cent(noon, ctx_at) == (pytest.approx(5.6), "SNAP")
    assert without.work_cent(noon, ctx_at) == (7.0, None)
    reasons = {(item.rule_id, item.reason, item.detail) for item in without.skipped}
    assert ("SNAP", SKIP_NO_QUARTER_HOUR_METER, None) in reasons
    assert ("WiNAP", SKIP_STATUS, "entwurf") in reasons  # not included by default


def test_metering_selects_the_base_price(ctx_at):
    catalog = parse_grid_fee_catalog(CATALOG)
    metered = resolve_grid_fee(parse_grid_fee_config({"area_id": "AT-PLAIN", "power_metering": "metered_power"}), catalog)
    assert metered.base_cent_kwh == 3.0
    assert resolve_grid_fee(parse_grid_fee_config({"area_id": "AT-PLAIN"}), catalog).base_cent_kwh == 5.0


def test_included_rule_without_value_is_an_error():
    catalog = parse_grid_fee_catalog(CATALOG)
    config = parse_grid_fee_config({"area_id": "AT-VBG", "quarter_hour_meter": True, "include_status": ["verordnet", "entwurf"]})
    assert code_of(resolve_grid_fee, config, catalog) == ErrorCode.RULE_VALUE_MISSING


def test_unknown_area_and_missing_catalog():
    catalog = parse_grid_fee_catalog(CATALOG)
    assert code_of(resolve_grid_fee, parse_grid_fee_config({"area_id": "AT-XX"}), catalog) == ErrorCode.GRID_AREA_UNKNOWN
    assert code_of(resolve_grid_fee, parse_grid_fee_config({"area_id": "AT-VBG"}), None) == ErrorCode.GRID_AREA_UNKNOWN


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ({"colour": 1}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({"power_metering": "none"}, ErrorCode.VALUE_INVALID),
        ({"base_cent_kwh": -1}, ErrorCode.VALUE_INVALID),
        ({"include_status": ["maybe"]}, ErrorCode.VALUE_INVALID),
        ({"area_id": "AT-VBG", "rules": [{"id": "r", "effect": {"mode": "add_cent", "value": 1}}]}, ErrorCode.VALUE_INVALID),
        ({"rules": [{"id": "r", "effect": {"mode": "add_cent", "value": 1}, "when_market_cent_kwh": {"below": 0}}]}, ErrorCode.RULE_UNKNOWN_FIELD),
        ({"rules": [{"id": "r", "effect": {"mode": "add_cent", "value": None}}]}, ErrorCode.RULE_VALUE_MISSING),
    ],
)  # fmt: skip
def test_invalid_config(raw, code):
    if code == ErrorCode.RULE_VALUE_MISSING:
        config = parse_grid_fee_config(raw)  # null value is allowed to parse, not to resolve
        assert code_of(resolve_grid_fee, config) == code
    else:
        assert code_of(parse_grid_fee_config, raw) == code


def test_invalid_catalog():
    broken = {**CATALOG, "areas": [{**CATALOG["areas"][0], "rule_set": "NOPE"}]}
    assert code_of(parse_grid_fee_catalog, broken) == ErrorCode.VALUE_INVALID
    no_status = {"rule_sets": {"S": [{"id": "r", "effect": {"mode": "add_cent", "value": 1}}]}}
    assert code_of(parse_grid_fee_catalog, no_status) == ErrorCode.FIELD_MISSING
    duplicate = {**CATALOG, "areas": [CATALOG["areas"][0], CATALOG["areas"][0]]}
    assert code_of(parse_grid_fee_catalog, duplicate) == ErrorCode.VALUE_INVALID
    assert code_of(parse_grid_fee_catalog, {"areas": [], "rules": []}) == ErrorCode.TARIFF_UNKNOWN_FIELD


def test_grid_rules_use_the_holiday_calendar(ctx_de, ctx_plain):
    config = parse_grid_fee_config({"base_cent_kwh": 9.0, "rules": [
        {"id": "we", "weekdays": "weekend", "effect": {"mode": "absolute_cent", "value": 4.0}}]})  # fmt: skip
    fee = resolve_grid_fee(config)
    christmas = at("2026-12-25 12:00")  # Friday
    assert fee.work_cent(ctx_de.to_local(christmas), ctx_de) == (4.0, "we")
    assert code_of(fee.work_cent, ctx_plain.to_local(christmas), ctx_plain) == ErrorCode.HOLIDAY_REGION_MISSING
