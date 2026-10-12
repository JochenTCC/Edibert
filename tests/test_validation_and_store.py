"""Strict validation (fail loud), holiday region handling, loading of catalog and user files."""

import json

import pytest
from conftest import at, load_example, make

from edbert.context import PricingContext
from edbert.errors import EdbertError, ErrorCode
from edbert.store import load_tariffs
from edbert.tariff import EXPORT, IMPORT, parse_tariff, price_cent

BASE = {"id": "t", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0}
EFFECT = {"mode": "add_cent", "value": 1}


def code_of(func, *args, **kwargs):
    with pytest.raises(EdbertError) as err:
        func(*args, **kwargs)
    return err.value.code


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ({**BASE, "colour": "red"}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({**BASE, "tiers": [{"upTo": 10, "rate": 1}]}, ErrorCode.UNSUPPORTED_FEATURE),
        ({**BASE, "applies_to": "heat_pump_meter"}, ErrorCode.UNSUPPORTED_FEATURE),
        ({k: v for k, v in BASE.items() if k != "fix_cent_kwh"}, ErrorCode.FIELD_MISSING),
        ({**BASE, "type": "gold"}, ErrorCode.VALUE_INVALID),
        ({**BASE, "price_floor_cent_kwh": 10, "price_cap_cent_kwh": 5}, ErrorCode.VALUE_INVALID),
        ({**BASE, "fix_cent_kwh": float("nan")}, ErrorCode.VALUE_INVALID),
        ({**BASE, "prices_include_vat": "yes"}, ErrorCode.VALUE_INVALID),
        ({**BASE, "rules": [{"id": "r", "effect": EFFECT, "colour": 1}]}, ErrorCode.RULE_UNKNOWN_FIELD),
        ({**BASE, "rules": [{"id": "r"}]}, ErrorCode.FIELD_MISSING),
        ({**BASE, "rules": [{"id": "r", "effect": {"mode": "free", "value": 1}}]}, ErrorCode.VALUE_INVALID),
        ({**BASE, "rules": [{"id": "r", "effect": {"mode": "percent_off", "value": 120}}]}, ErrorCode.VALUE_INVALID),
        ({**BASE, "rules": [{"id": "r", "effect": EFFECT, "time": {"from": "10:00", "to": "10:00"}}]}, ErrorCode.VALUE_INVALID),
        ({**BASE, "rules": [{"id": "r", "effect": EFFECT, "time": {"from": "25:00", "to": "10:00"}}]}, ErrorCode.VALUE_INVALID),
        ({**BASE, "rules": [{"id": "r", "effect": EFFECT, "months": [0]}]}, ErrorCode.VALUE_INVALID),
        ({**BASE, "rules": [{"id": "r", "effect": EFFECT, "weekdays": ["funday"]}]}, ErrorCode.VALUE_INVALID),
        ({**BASE, "rules": [{"id": "r", "effect": EFFECT, "when_market_cent_kwh": {"below": 1, "above": 2}}]}, ErrorCode.VALUE_INVALID),
        ({**BASE, "rules": [{"id": "r", "effect": EFFECT}, {"id": "r", "effect": EFFECT}]}, ErrorCode.VALUE_INVALID),
        ({**BASE, "holidays": {"treat_as": "monday"}}, ErrorCode.VALUE_INVALID),
        ({**BASE, "requires": ["jetpack"]}, ErrorCode.VALUE_INVALID),
    ],
)  # fmt: skip
def test_invalid_tariffs_fail_with_a_code(raw, code):
    assert code_of(parse_tariff, raw, IMPORT) == code


def test_export_only_type_is_rejected_for_import():
    assert code_of(parse_tariff, {"id": "x", "type": "fixed", "supplier_id": "s", "k_push_cent": 5}, IMPORT) == ErrorCode.VALUE_INVALID
    assert parse_tariff({"id": "x", "type": "fixed", "supplier_id": "s", "k_push_cent": 5}, EXPORT).k_push_cent == 5


def test_weekday_words_and_groups_are_accepted():
    tariff = make(BASE, rules=[{"id": "r", "effect": EFFECT, "weekdays": ["mon", "weekend", "holiday"]}])
    assert tariff.rules[0].weekdays == frozenset({0, 5, 6, "holiday"})


def test_comment_fields_are_ignored_everywhere():
    tariff = make({**BASE, "$comment": "hello"}, rules=[{"id": "r", "$comment": "x", "effect": EFFECT}])
    assert tariff.id == "t"


def test_region_is_only_required_when_holidays_can_matter(ctx_plain):
    no_weekday_filter = make(BASE, rules=[{"id": "r", "effect": EFFECT}])
    assert no_weekday_filter.needs_calendar is False
    assert price_cent(no_weekday_filter, at("2026-12-25 12:00"), ctx_plain) == 31.0
    weekend = make(BASE, rules=[{"id": "r", "effect": EFFECT, "weekdays": "weekend"}])
    assert weekend.needs_calendar is True
    assert code_of(price_cent, weekend, at("2026-12-25 12:00"), ctx_plain) == ErrorCode.HOLIDAY_REGION_MISSING


def test_unknown_holiday_region_is_an_error():
    weekend = make(BASE, rules=[{"id": "r", "effect": EFFECT, "weekdays": "weekend"}])
    ctx = PricingContext("Europe/Berlin", "DE", "XX")
    assert code_of(price_cent, weekend, at("2026-12-25 12:00"), ctx) == ErrorCode.HOLIDAY_REGION_UNKNOWN


def test_invalid_timezone_is_an_error():
    assert code_of(PricingContext, "Mars/Olympus") == ErrorCode.VALUE_INVALID


def test_all_example_tariffs_parse():
    for name, direction in (
        ("fixed_day_night.json", IMPORT),
        ("spot_evening_surcharge_cap.json", IMPORT),
        ("export_no_pay_at_negative_price.json", EXPORT),
    ):
        assert parse_tariff(load_example(name), direction).rules


def write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_load_catalog_and_user_file(tmp_path):
    catalog = write(tmp_path / "tariffs.json", {"catalog_as_of": "2026", "import_tariffs": [BASE]})
    user = write(tmp_path / "user_tariffs.json", {"import_tariffs": [{**BASE, "id": "user_mine"}]})
    result = load_tariffs(catalog, user)
    assert set(result.imports) == {"t", "user_mine"}
    assert result.origin[(IMPORT, "user_mine")] == "user"
    assert result.get(IMPORT, "t").fix_cent_kwh == 30.0


def test_user_file_is_optional(tmp_path):
    catalog = write(tmp_path / "tariffs.json", {"import_tariffs": [BASE]})
    assert set(load_tariffs(catalog, tmp_path / "missing.json").imports) == {"t"}


def test_id_rules(tmp_path):
    user_bad = write(tmp_path / "u1.json", {"import_tariffs": [BASE]})
    assert code_of(load_tariffs, None, user_bad) == ErrorCode.ID_PREFIX_MISSING
    catalog_bad = write(tmp_path / "c1.json", {"import_tariffs": [{**BASE, "id": "user_x"}]})
    assert code_of(load_tariffs, catalog_bad, None) == ErrorCode.ID_PREFIX_RESERVED
    duplicate = write(tmp_path / "c2.json", {"import_tariffs": [BASE, BASE]})
    assert code_of(load_tariffs, duplicate, None) == ErrorCode.ID_COLLISION


def test_broken_files_and_root_fields(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{ not json", encoding="utf-8")
    assert code_of(load_tariffs, broken, None) == ErrorCode.FILE_INVALID
    unknown_root = write(tmp_path / "root.json", {"import_tarifs": []})
    assert code_of(load_tariffs, unknown_root, None) == ErrorCode.TARIFF_UNKNOWN_FIELD
    assert code_of(load_tariffs, tmp_path / "does_not_exist.json", None) == ErrorCode.FILE_INVALID
