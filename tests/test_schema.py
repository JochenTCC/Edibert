import json
from pathlib import Path

import pytest
from conftest import load_example
from jsonschema import Draft202012Validator

from edbert.schema import rule_field_names, tariff_field_names, tariff_schema

COMMITTED = Path(__file__).resolve().parent.parent / "schema" / "tariff.schema.json"
EXAMPLE_FILES = ("fixed_day_night.json", "spot_evening_surcharge_cap.json", "export_no_pay_at_negative_price.json")


def test_schema_is_valid_and_fields_agree_with_the_parser():
    schema = tariff_schema()
    Draft202012Validator.check_schema(schema)
    assert set(schema["properties"]) == set(tariff_field_names()) | {"$comment"}
    rule_properties = schema["properties"]["rules"]["items"]["properties"]
    assert set(rule_properties) == set(rule_field_names()) | {"$comment"}


@pytest.mark.parametrize("name", EXAMPLE_FILES)
def test_examples_validate(name):
    Draft202012Validator(tariff_schema()).validate(load_example(name))


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "x", "type": "fixed_cent", "supplier_id": "s", "colour": 1},
        {"id": "x", "type": "gold", "supplier_id": "s"},
        {"id": "x", "type": "fixed_cent", "supplier_id": "s", "applies_to": "meter"},
        {"id": "x", "type": "fixed_cent", "supplier_id": "s", "rules": [{"id": "r"}]},
        {"id": "x", "type": "fixed_cent", "supplier_id": "s", "rules": [{"id": "r", "effect": {"mode": "free", "value": 1}}]},
    ],
)
def test_schema_rejects_bad_tariffs(bad):
    assert not Draft202012Validator(tariff_schema()).is_valid(bad)


def test_committed_schema_is_current():
    assert json.loads(COMMITTED.read_text(encoding="utf-8")) == tariff_schema(), (
        "schema/tariff.schema.json is stale: run `python -m edbert schema > schema/tariff.schema.json`"
    )
