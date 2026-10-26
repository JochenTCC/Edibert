"""Grid fee: catalog and user grid areas, the area selection in the house profile, status and meter handling."""

import json

import pytest
from conftest import EXAMPLES, at, flat_grid_fee, load_example, make

from edibert.errors import EdibertError, ErrorCode
from edibert.gridfee import (
    CATALOG,
    SKIP_NO_QUARTER_HOUR_METER,
    SKIP_STATUS,
    USER,
    flat_user_grid_area,
    load_grid_fee_catalog,
    load_grid_fee_config,
    load_grid_fees,
    merge_grid_fee_catalogs,
    parse_grid_fee_catalog,
    parse_grid_fee_config,
    resolve_grid_fee,
    save_user_grid_area,
)
from edibert.tariff import evaluate, price_cent

CATALOG_DOC = {
    "tariff_format": 1,
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
USER_DOC = {"tariff_format": 1, "areas": [flat_user_grid_area("user_home", 5.353, label="Home", land="AT")]}


def code_of(func, *args, **kwargs):
    with pytest.raises(EdibertError) as err:
        func(*args, **kwargs)
    return err.value.code


def catalog() -> object:
    return parse_grid_fee_catalog(CATALOG_DOC)


def test_modul3_example_levels(ctx_de):
    areas = parse_grid_fee_catalog(load_example("grid_fee_modul3_example.json"), USER)
    config = parse_grid_fee_config(load_example("netznutzung_modul3_example.json")["netznutzung"])
    fee = resolve_grid_fee(config, areas)
    assert fee.work_cent(ctx_de.to_local(at("2026-10-12 03:00")), ctx_de) == (1.0, "nt")
    assert fee.work_cent(ctx_de.to_local(at("2026-10-12 12:00")), ctx_de) == (9.98, None)
    assert fee.work_cent(ctx_de.to_local(at("2026-10-12 16:00")), ctx_de) == (14.92, "ht")
    assert fee.work_cent(ctx_de.to_local(at("2026-10-12 20:00")), ctx_de) == (9.98, None)  # end exclusive


def test_example_file_loader_accepts_wrapper_and_bare_object(tmp_path):
    wrapped = load_grid_fee_config(EXAMPLES / "netznutzung_modul3_example.json")
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps(load_example("netznutzung_modul3_example.json")["netznutzung"]), encoding="utf-8")
    assert load_grid_fee_config(bare) == wrapped


def test_grid_fee_is_added_before_vat(ctx_plain):
    spot = make({"id": "s", "type": "spot_hourly", "supplier_id": "x", "settlement_fee_cent_kwh": 1.0,
                 "prices_include_vat": False, "vat_percent": 20.0})  # fmt: skip
    result = evaluate(spot, at("2026-10-12 12:00"), ctx_plain, epex_cent=10.0, grid_fee=flat_grid_fee(8.0))
    assert result.after_limits_cent == 11.0
    assert result.grid_cent == 8.0
    assert result.cent == pytest.approx((11.0 + 8.0) * 1.2)


def test_grid_fee_is_not_applied_to_export(ctx_plain):
    export = make({"id": "e", "type": "fixed", "supplier_id": "s", "k_push_cent": 5.0, "vat_percent": 0}, direction="export")
    assert price_cent(export, at("2026-10-12 12:00"), ctx_plain, grid_fee=flat_grid_fee(8.0)) == 5.0


def test_catalog_area_snap_needs_quarter_hour_meter(ctx_at):
    with_meter = resolve_grid_fee(parse_grid_fee_config({"area_id": "AT-VBG", "quarter_hour_meter": True}), catalog())
    without = resolve_grid_fee(parse_grid_fee_config({"area_id": "AT-VBG"}), catalog())
    noon = ctx_at.to_local(at("2026-07-15 12:00"))
    assert with_meter.work_cent(noon, ctx_at) == (pytest.approx(5.6), "SNAP")
    assert without.work_cent(noon, ctx_at) == (7.0, None)
    reasons = {(item.rule_id, item.reason, item.detail) for item in without.skipped}
    assert ("SNAP", SKIP_NO_QUARTER_HOUR_METER, None) in reasons
    assert ("WiNAP", SKIP_STATUS, "entwurf") in reasons  # not included by default


def test_metering_selects_the_base_price():
    metered = resolve_grid_fee(parse_grid_fee_config({"area_id": "AT-PLAIN", "power_metering": "metered_power"}), catalog())
    assert metered.base_cent_kwh == 3.0
    assert resolve_grid_fee(parse_grid_fee_config({"area_id": "AT-PLAIN"}), catalog()).base_cent_kwh == 5.0


def test_included_rule_without_value_is_an_error():
    config = parse_grid_fee_config({"area_id": "AT-VBG", "quarter_hour_meter": True, "include_status": ["verordnet", "entwurf"]})
    assert code_of(resolve_grid_fee, config, catalog()) == ErrorCode.RULE_VALUE_MISSING


def test_unknown_area():
    assert code_of(resolve_grid_fee, parse_grid_fee_config({"area_id": "AT-XX"}), catalog()) == ErrorCode.GRID_AREA_UNKNOWN


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (None, ErrorCode.FIELD_MISSING),
        ({}, ErrorCode.FIELD_MISSING),
        ({"area_id": None}, ErrorCode.FIELD_MISSING),
        ({"area_id": "AT-VBG", "colour": 1}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({"area_id": "AT-VBG", "power_metering": "none"}, ErrorCode.VALUE_INVALID),
        ({"area_id": "AT-VBG", "include_status": ["maybe"]}, ErrorCode.VALUE_INVALID),
        # own values moved to user grid areas; the old fields are unknown now
        ({"area_id": None, "base_cent_kwh": 5.0}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({"area_id": "user_x", "rules": []}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({"area_id": "user_x", "holidays": {"treat_as": "sunday"}}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({"area_id": "user_x", "extra_holiday_dates": []}, ErrorCode.TARIFF_UNKNOWN_FIELD),
    ],
)  # fmt: skip
def test_invalid_config(raw, code):
    assert code_of(parse_grid_fee_config, raw) == code


def test_invalid_catalog():
    broken = {**CATALOG_DOC, "areas": [{**CATALOG_DOC["areas"][0], "rule_set": "NOPE"}]}
    assert code_of(parse_grid_fee_catalog, broken) == ErrorCode.VALUE_INVALID
    no_status = {"tariff_format": 1, "rule_sets": {"S": [{"id": "r", "effect": {"mode": "add_cent", "value": 1}}]}}
    assert code_of(parse_grid_fee_catalog, no_status) == ErrorCode.FIELD_MISSING
    duplicate = {**CATALOG_DOC, "areas": [CATALOG_DOC["areas"][0], CATALOG_DOC["areas"][0]]}
    assert code_of(parse_grid_fee_catalog, duplicate) == ErrorCode.GRID_ID_COLLISION
    assert code_of(parse_grid_fee_catalog, {"tariff_format": 1, "areas": [], "rules": []}) == ErrorCode.TARIFF_UNKNOWN_FIELD


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"areas": []}, ErrorCode.FORMAT_MISSING),
        ({"tariff_format": 2, "areas": []}, ErrorCode.FORMAT_UNSUPPORTED),
        ({"tariff_format": "1", "areas": []}, ErrorCode.FORMAT_UNSUPPORTED),
        ({"tariff_format": True, "areas": []}, ErrorCode.FORMAT_UNSUPPORTED),
        ({"tariff_format": 1, "earnie_data_model": 4, "areas": []}, ErrorCode.TARIFF_UNKNOWN_FIELD),
    ],
)  # fmt: skip
def test_grid_files_need_the_tariff_format(document, code):
    assert code_of(parse_grid_fee_catalog, document) == code
    assert code_of(parse_grid_fee_catalog, document, USER) == code


def test_format_error_names_the_file_and_the_supported_versions():
    with pytest.raises(EdibertError) as err:
        parse_grid_fee_catalog({"tariff_format": 7}, USER, "user_grid_fees.json")
    assert err.value.params == {"path": "user_grid_fees.json", "value": 7, "supported": "1"}


def test_user_rules_need_no_status_and_always_apply(ctx_plain):
    document = {"tariff_format": 1, "rule_sets": {"user_night": [
        {"id": "night", "time": {"from": "00:00", "to": "06:00"}, "effect": {"mode": "absolute_cent", "value": 2.0}}]},
        "areas": [{"id": "user_a", "base_cent_kwh": {"unmetered_power": 6.0, "metered_power": 6.0}, "rule_set": "user_night"}]}  # fmt: skip
    fee = resolve_grid_fee(parse_grid_fee_config({"area_id": "user_a"}), parse_grid_fee_catalog(document, USER))
    assert fee.work_cent(ctx_plain.to_local(at("2026-10-12 03:00")), ctx_plain) == (2.0, "night")
    assert code_of(parse_grid_fee_catalog, document, CATALOG) == ErrorCode.GRID_ID_PREFIX_RESERVED


@pytest.mark.parametrize(
    ("document", "origin", "code"),
    [
        ({"tariff_format": 1, "areas": [flat_user_grid_area("home", 5.0)]}, USER, ErrorCode.GRID_ID_PREFIX_MISSING),
        ({"tariff_format": 1, "rule_sets": {"night": []}}, USER, ErrorCode.GRID_ID_PREFIX_MISSING),
        ({"tariff_format": 1, "areas": [flat_user_grid_area("user_x", 5.0)]}, CATALOG, ErrorCode.GRID_ID_PREFIX_RESERVED),
        ({"tariff_format": 1, "rule_sets": {"user_s": []}}, CATALOG, ErrorCode.GRID_ID_PREFIX_RESERVED),
    ],
)  # fmt: skip
def test_grid_id_prefix_rules(document, origin, code):
    assert code_of(parse_grid_fee_catalog, document, origin) == code


def test_merged_view_keeps_the_origin_and_resolves_user_areas():
    merged = merge_grid_fee_catalogs(catalog(), parse_grid_fee_catalog(USER_DOC, USER))
    assert merged.origin == {"AT-VBG": "catalog", "AT-PLAIN": "catalog", "user_home": "user"}
    fee = resolve_grid_fee(parse_grid_fee_config({"area_id": "user_home", "power_metering": "metered_power"}), merged)
    assert (fee.base_cent_kwh, fee.rules) == (5.353, ())


def test_an_id_in_both_files_is_a_collision():
    # The prefix rules already keep the files apart; the merge checks anyway.
    user = parse_grid_fee_catalog(USER_DOC, USER)
    assert code_of(merge_grid_fee_catalogs, user, user) == ErrorCode.GRID_ID_COLLISION


def test_load_grid_fees_tolerates_a_missing_user_file(tmp_path):
    grid = tmp_path / "grid_fees.json"
    grid.write_text(json.dumps(CATALOG_DOC), encoding="utf-8")
    user = tmp_path / "user_grid_fees.json"
    assert set(load_grid_fees(grid, user).areas) == {"AT-VBG", "AT-PLAIN"}
    user.write_text(json.dumps(USER_DOC), encoding="utf-8")
    assert load_grid_fees(grid, user).origin["user_home"] == "user"
    assert set(load_grid_fees(None, user).areas) == {"user_home"}
    assert load_grid_fee_catalog(grid).origin == {"AT-VBG": "catalog", "AT-PLAIN": "catalog"}


def test_save_user_grid_area_creates_replaces_and_validates(tmp_path):
    path = tmp_path / "data" / "user_grid_fees.json"
    save_user_grid_area(path, flat_user_grid_area("user_a", 5.0))
    save_user_grid_area(path, flat_user_grid_area("user_b", 6.0))
    save_user_grid_area(path, flat_user_grid_area("user_a", 4.0, label="A"))  # same ID replaces
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["tariff_format"] == 1
    assert [(area["id"], area["base_cent_kwh"]["metered_power"]) for area in document["areas"]] == [("user_b", 6.0), ("user_a", 4.0)]
    before = path.read_text(encoding="utf-8")
    assert code_of(save_user_grid_area, path, flat_user_grid_area("home", 5.0)) == ErrorCode.GRID_ID_PREFIX_MISSING
    assert code_of(save_user_grid_area, path, flat_user_grid_area("user_c", -1.0)) == ErrorCode.VALUE_INVALID
    assert code_of(save_user_grid_area, path, {**flat_user_grid_area("user_c", 1.0), "rule_set": "user_none"}) == ErrorCode.VALUE_INVALID
    assert path.read_text(encoding="utf-8") == before


def test_save_user_grid_area_refuses_an_unmigrated_file(tmp_path):
    path = tmp_path / "user_grid_fees.json"
    path.write_text(json.dumps({"areas": []}), encoding="utf-8")
    assert code_of(save_user_grid_area, path, flat_user_grid_area("user_a", 5.0)) == ErrorCode.FORMAT_MISSING
    assert json.loads(path.read_text(encoding="utf-8")) == {"areas": []}


def test_grid_rules_use_the_holiday_calendar(ctx_de, ctx_plain):
    document = {"tariff_format": 1, "rule_sets": {"user_we": [
        {"id": "we", "weekdays": "weekend", "effect": {"mode": "absolute_cent", "value": 4.0}}]},
        "areas": [{"id": "user_a", "base_cent_kwh": {"unmetered_power": 9.0, "metered_power": 9.0}, "rule_set": "user_we"}]}  # fmt: skip
    fee = resolve_grid_fee(parse_grid_fee_config({"area_id": "user_a"}), parse_grid_fee_catalog(document, USER))
    christmas = at("2026-12-25 12:00")  # Friday
    assert fee.work_cent(ctx_de.to_local(christmas), ctx_de) == (4.0, "we")
    assert code_of(fee.work_cent, ctx_plain.to_local(christmas), ctx_plain) == ErrorCode.HOLIDAY_REGION_MISSING
