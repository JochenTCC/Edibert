"""Editor form model: form values <-> tariff JSON, templates."""

import pytest
from conftest import load_example

from edibert.editor.model import RuleDraft, TariffDraft, slugify, validate
from edibert.editor.templates import TEMPLATES, rules_for_template
from edibert.errors import ErrorCode
from edibert.i18n import Translator
from edibert.tariff import EXPORT, IMPORT, parse_tariff


@pytest.mark.parametrize(
    ("name", "direction"),
    [("fixed_day_night.json", IMPORT), ("spot_evening_surcharge_cap.json", IMPORT), ("export_no_pay_at_negative_price.json", EXPORT)],
)
def test_form_roundtrip_keeps_the_tariff(name, direction):
    raw = load_example(name)
    again = TariffDraft.from_raw(raw, direction).to_raw()
    assert parse_tariff(again, direction) == parse_tariff(raw, direction)


def test_unknown_fields_survive_the_form():
    raw = {"id": "user_x", "label": "X", "type": "monthly_table", "supplier_id": "user_s", "monthly_seed": {"curve": "oemag"},
           "monthly_rates": [{"year": 2026, "month": 10, "tariff_cent_kwh": 9.0}]}  # fmt: skip
    draft = TariffDraft.from_raw(raw, EXPORT)
    assert draft.kind == "monthly"
    assert draft.to_raw()["monthly_seed"] == {"curve": "oemag"}
    assert validate(draft).ok


def test_new_draft_builds_a_valid_user_tariff():
    draft = TariffDraft(label="Mein Stadtwerk Tag/Nacht", supplier="Stadtwerk Beispiel", price_cent=30.0, vat_percent=19)
    result = validate(draft, taken={"user_mein_stadtwerk_tag_nacht"})
    assert result.ok
    assert result.raw["id"] == "user_mein_stadtwerk_tag_nacht_2"
    assert result.raw["supplier_id"] == "user_stadtwerk_beispiel"
    assert result.raw["type"] == "fixed_cent"


def test_slugify_handles_umlauts():
    assert slugify("Größe & Gäste: Tarif!") == "groesse_gaeste_tarif"
    assert slugify("???") == "tariff"


def test_days_are_normalized_to_groups_and_omitted_when_every_day():
    rule = RuleDraft.from_raw({"id": "r", "weekdays": [0, 1, 2, 3, 4], "effect": {"mode": "add_cent", "value": 1}})
    assert rule.days == ["mon", "tue", "wed", "thu", "fri"]
    assert rule.to_raw("x")["weekdays"] == "weekday"
    assert RuleDraft(id="a", days=["sat", "sun"]).to_raw("x")["weekdays"] == "weekend"
    assert "weekdays" not in RuleDraft(id="a", days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"]).to_raw("x")
    assert RuleDraft(id="a", days=["sat", "holiday"]).to_raw("x")["weekdays"] == ["sat", "holiday"]


def test_rule_months_and_time_are_optional():
    raw = RuleDraft(id="a", label="A", months=list(range(1, 13)), value=3).to_raw("x")
    assert "months" not in raw
    assert "time" not in raw
    assert RuleDraft(id="a", start="10:00", end="16:00", months=[7, 4]).to_raw("x")["months"] == [4, 7]


def test_validate_reports_the_first_coded_problem():
    draft = TariffDraft(label="x", price_cent=30.0, rules=[RuleDraft(id="bad", start="25:00", end="06:00")])
    result = validate(draft)
    assert not result.ok
    assert result.error is not None
    assert result.error.code == ErrorCode.VALUE_INVALID
    assert "time.from" in result.error.params["field"]


def test_spot_and_export_fields_end_up_in_the_right_place():
    spot = TariffDraft(label="s", kind="spot", markup_percent=3.0, fee_cent=1.5, prices_include_vat=False, vat_percent=20)
    raw = spot.to_raw()
    assert (raw["type"], raw["markup_percent"], raw["settlement_fee_cent_kwh"]) == ("spot_hourly", 3.0, 1.5)
    export = TariffDraft(direction=EXPORT, label="e", kind="spot", feed_in_fee_factor=0.19, feed_in_fix_cent=0.5, price_floor_cent_kwh=0.0)
    raw = export.to_raw()
    assert (raw["feed_in_fee_factor"], raw["feed_in_fix_cent"], raw["price_floor_cent_kwh"]) == (0.19, 0.5, 0.0)
    assert "markup_percent" not in raw
    assert validate(export).ok


@pytest.mark.parametrize("name", TEMPLATES)
def test_templates_produce_valid_rows(name):
    for kind, mode in (("fixed", "absolute_cent"), ("spot", "add_cent")):
        rules = rules_for_template(name, Translator("de"), kind=kind, base_cent=30.0)
        assert rules
        assert {rule.mode for rule in rules} == {mode}
        draft = TariffDraft(label="t", kind=kind, price_cent=30.0, rules=rules, prices_include_vat=kind == "fixed")
        assert validate(draft).ok, name


def test_template_labels_follow_the_language_and_ids_stay_unique():
    de = rules_for_template("night", Translator("de"), kind="fixed", base_cent=30.0)
    en = rules_for_template("night", Translator("en"), kind="fixed", base_cent=30.0, taken_ids={"night"})
    assert de[0].label == "Nachttarif"
    assert en[0].label == "Night tariff"
    assert de[0].id == "night"
    assert en[0].id == "night_2"
    assert de[0].value == 24.0  # 30 * 0.8, a suggestion to correct


def test_unknown_template_is_an_error():
    translator = Translator("en")
    with pytest.raises(ValueError):
        rules_for_template("nope", translator, kind="fixed", base_cent=30.0)


def test_a_tariff_needs_a_name():
    result = validate(TariffDraft(label="  ", price_cent=30.0))
    assert not result.ok
    assert result.error is not None
    assert (result.error.code, result.error.params["field"]) == (ErrorCode.FIELD_MISSING, "label")
