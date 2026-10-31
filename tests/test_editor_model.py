"""Editor form model: form values <-> tariff JSON, templates."""

import json

import pytest
from conftest import load_example

from edibert.editor.model import RuleDraft, TariffDraft, slugify, validate
from edibert.editor.templates import TEMPLATES, rules_for_template
from edibert.errors import EdibertError, ErrorCode
from edibert.gridfee import GridFeeCatalog
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
    raw = {"id": "user_x", "label": "X", "type": "monthly_table", "supplier_id": "user_s", "vat_percent": 0, "monthly_seed": {"curve": "oemag"},
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


def test_own_grid_values_are_the_user_area_user_house(ctx_plain):
    from conftest import at

    from edibert.editor.house import (
        HOUSE_GRID_AREA,
        GridDraft,
        HouseSettings,
        PartDraft,
    )
    from edibert.gridfee import USER, parse_grid_fee_catalog

    night = RuleDraft(id="night", start="00:00", end="06:00", value=2.0)
    draft = GridDraft(base={"unmetered_power": 8.0, "metered_power": 8.0}, rules=[night],
                      components=[PartDraft(label="Loss", values={"unmetered_power": 0.4, "metered_power": 0.4})],
                      fixed=[PartDraft(label="Base fee", values={"unmetered_power": 54.0, "metered_power": None})])
    house = HouseSettings(grid_area_id=HOUSE_GRID_AREA)
    fee = draft.resolve(house)
    assert fee.area_id == HOUSE_GRID_AREA
    assert fee.work_cent(ctx_plain.to_local(at("2026-10-12 03:00")), ctx_plain) == (2.0, "night")
    slot = fee.slot(ctx_plain.to_local(at("2026-10-12 12:00")), ctx_plain)
    assert (slot.total_cent, slot.breakdown) == (8.4, (("work", 8.0), ("component_1", 0.4)))
    assert fee.fixed_eur_year == 54.0
    document = draft.document()
    assert document["tariff_format"] == 1 and document["areas"][0]["rule_set"] == HOUSE_GRID_AREA
    grids = parse_grid_fee_catalog(document, USER)
    assert HouseSettings(grid_area_id=None).grid_fee(grids) is None  # no grid fee
    metered = HouseSettings(grid_area_id=HOUSE_GRID_AREA, power_metering="metered_power")
    with pytest.raises(EdibertError) as err:
        metered.grid_fee(grids)  # the base fee of metered power is not modeled: an error, never 0
    assert err.value.code == ErrorCode.GRID_METERING_NOT_MODELED


def test_legacy_house_grid_fee_is_not_read_silently(tmp_path):
    from edibert.editor.house import load_house

    path = tmp_path / "house.json"
    path.write_text(json.dumps({"land": "AT", "grid_enabled": True, "grid_base_cent": 5.0, "grid_rules": []}), encoding="utf-8")
    house = load_house(path)
    with pytest.raises(EdibertError) as err:
        house.grid_fee(GridFeeCatalog({}, {}))
    assert err.value.code == ErrorCode.HOUSE_GRID_LEGACY
    areas, rule_sets, own = house.legacy_migration_input()
    assert own == "user_house" and areas[0]["base_cent_kwh"]["unmetered_power"] == 5.0 and rule_sets == {}
    assert house.migrated().to_json()["grid_area_id"] == "user_house"
