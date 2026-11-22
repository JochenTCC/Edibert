"""AppTests of every edit path of the tariff form: all four steps, both directions, all price kinds, the rule rows,
the grid-fee parts, the preview tools, and invalid input (coded error, no save button, nothing written).

Complements tests/test_ui_app.py (main flows) with the field-by-field coverage of the form.
"""

import json
from datetime import date

import pytest

pytest.importorskip("streamlit")
from overview_helpers import labels, open_own, run_action, select_keys, show_view
from streamlit.testing.v1 import AppTest
from test_ui_app import create_fixed_tariff, start, widget_key

from edibert.ui.config import ENV_CATALOG, ENV_DATA_DIR, ENV_LANG


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv(ENV_LANG, "en")
    monkeypatch.delenv(ENV_CATALOG, raising=False)
    return tmp_path / "data"


def saved(data_dir, direction: str = "import") -> list[dict]:
    path = data_dir / "user_tariffs.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))[f"{direction}_tariffs"]


def has_save(app: AppTest) -> bool:
    return any(button.key == "ui.save" for button in app.button)


def save(app: AppTest) -> None:
    assert not app.error, [item.value for item in app.error]
    app.button(key="ui.save").click().run()
    assert not app.exception


def step(app: AppTest, number: int) -> None:
    app.radio(key="ui.step_radio").set_value(number).run()


def new(app: AppTest, direction: str, label: str) -> None:
    app.button(key=f"new.{direction}").click().run()
    app.text_input(key=widget_key(app, "label")).set_value(label).run()


def rule_keys(app: AppTest, field: str) -> list[str]:
    """Keys of the rule-row widgets ``field`` of the tariff form, in the order shown."""
    prefix = widget_key(app, "rules") + ".r"
    widgets = [
        *app.text_input,
        *app.checkbox,
        *app.multiselect,
        *app.selectbox,
        *app.number_input,
        *app.time_input,
        *app.button,
    ]
    return [
        w.key
        for w in widgets
        if w.key and w.key.startswith(prefix) and w.key.endswith(f".{field}")
    ]


def expect_refused(app: AppTest, data_dir, fragment: str) -> None:
    """A coded error mentions ``fragment``, the save button is gone and nothing was written."""
    assert not app.exception
    assert any(fragment in item.value for item in app.error), [
        item.value for item in app.error
    ]
    assert not has_save(app)
    assert saved(data_dir) == []


# --- step 1: base price, direction and price kinds ---------------------------------------------------------------


def test_fixed_export_tariff_is_saved_as_feed_in(data_dir):
    app = start()
    new(app, "export", "Einspeisung")
    app.number_input(key=widget_key(app, "price")).set_value(7.5).run()
    app.checkbox(key=widget_key(app, "vat_included")).set_value(False).run()
    save(app)
    assert saved(data_dir) == []
    (tariff,) = saved(data_dir, "export")
    assert (tariff["type"], tariff["k_push_cent"], tariff["prices_include_vat"]) == (
        "fixed",
        7.5,
        False,
    )


def test_spot_import_fields_are_saved(data_dir):
    app = start()
    new(app, "import", "Spot Import")
    app.radio(key=widget_key(app, "kind")).set_value("spot").run()
    app.number_input(key=widget_key(app, "markup")).set_value(3.0).run()
    app.number_input(key=widget_key(app, "fee")).set_value(1.234).run()
    app.selectbox(key=widget_key(app, "mtu")).select("60min").run()
    save(app)
    (tariff,) = saved(data_dir)
    assert tariff["type"] == "spot_hourly"
    assert (
        tariff["markup_percent"],
        tariff["settlement_fee_cent_kwh"],
        tariff["settlement_mtu"],
    ) == (3.0, 1.234, "60min")


def test_spot_export_fields_are_saved(data_dir):
    app = start()
    new(app, "export", "Spot Feed")
    app.radio(key=widget_key(app, "kind")).set_value("spot").run()
    assert not [
        box for box in app.number_input if box.key == widget_key(app, "markup")
    ]  # import only
    app.number_input(key=widget_key(app, "fee_factor")).set_value(0.9).run()
    app.number_input(key=widget_key(app, "fee")).set_value(0.5).run()
    app.number_input(key=widget_key(app, "fix")).set_value(1.0).run()
    save(app)
    (tariff,) = saved(data_dir, "export")
    assert (
        tariff["feed_in_fee_factor"],
        tariff["settlement_fee_cent_kwh"],
        tariff["feed_in_fix_cent"],
    ) == (0.9, 0.5, 1.0)


def test_new_monthly_tariff_starts_with_the_current_month(data_dir):
    app = start()
    new(app, "import", "Monat")
    app.radio(key=widget_key(app, "kind")).set_value("monthly").run()
    assert not app.exception
    save(app)
    (tariff,) = saved(data_dir)
    today = date.today()
    assert tariff["type"] == "monthly_table"
    assert tariff["monthly_rates"] == [
        {"year": today.year, "month": today.month, "tariff_cent_kwh": 0.0}
    ]


def test_kind_switch_back_keeps_the_fixed_price(data_dir):
    app = start()
    create_fixed_tariff(app, "Wechsel", 22.5)
    app.radio(key=widget_key(app, "kind")).set_value("spot").run()
    app.radio(key=widget_key(app, "kind")).set_value("fixed").run()
    assert app.number_input(key=widget_key(app, "price")).value == 22.5
    save(app)
    (tariff,) = saved(data_dir)
    assert "settlement_mtu" not in tariff  # no spot leftovers in a fixed tariff


def test_supplier_and_regions_are_saved(data_dir):
    app = start()
    create_fixed_tariff(app, "Regional")
    app.text_input(key=widget_key(app, "supplier")).set_value("Stadtwerk Süd").run()
    app.selectbox(key=widget_key(app, "land")).select("DE").run()
    app.multiselect(key=widget_key(app, "regions.DE")).select("BY").select("BW").run()
    save(app)
    (tariff,) = saved(data_dir)
    assert tariff["supplier_id"] == "user_stadtwerk_sued"
    assert (tariff["land"], sorted(tariff["regions"])) == ("DE", ["BW", "BY"])


def test_land_change_drops_regions_of_the_old_land(data_dir):
    app = start()
    create_fixed_tariff(app, "Umzug")
    app.selectbox(key=widget_key(app, "land")).select("DE").run()
    app.multiselect(key=widget_key(app, "regions.DE")).select("BY").run()
    app.selectbox(key=widget_key(app, "land")).select("AT").run()
    assert app.multiselect(key=widget_key(app, "regions.AT")).value == []
    save(app)
    (tariff,) = saved(data_dir)
    assert tariff["land"] == "AT" and "regions" not in tariff


def test_vat_percent_is_saved_and_zero_is_allowed(data_dir):
    app = start()
    create_fixed_tariff(app, "Netto")
    app.checkbox(key=widget_key(app, "vat_included")).set_value(False).run()
    app.number_input(key=widget_key(app, "vat_percent")).set_value(0.0).run()
    save(app)
    (tariff,) = saved(data_dir)
    assert (tariff["prices_include_vat"], tariff["vat_percent"]) == (False, 0.0)


# --- invalid input in step 1 ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("label", ["", "   "])
def test_empty_or_blank_label_is_refused(data_dir, label):
    app = start()
    new(app, "import", label)
    expect_refused(app, data_dir, "name")


def test_negative_price_cannot_be_entered(data_dir):
    app = start()
    create_fixed_tariff(app, "Negativ")
    box = app.number_input(key=widget_key(app, "price"))
    assert box.min == 0.0


def test_same_label_twice_gets_a_second_id(data_dir):
    app = start()
    create_fixed_tariff(app, "Doppelt", 20.0)
    save(app)
    create_fixed_tariff(app, "Doppelt", 21.0)
    save(app)
    assert [tariff["id"] for tariff in saved(data_dir)] == [
        "user_doppelt",
        "user_doppelt_2",
    ]


def test_opened_tariff_is_saved_under_its_id_without_a_duplicate(data_dir):
    app = start()
    create_fixed_tariff(app, "Bestand", 20.0)
    save(app)
    open_own(app, "import", "user_bestand")
    assert app.number_input(key=widget_key(app, "price")).value == 20.0
    app.text_input(key=widget_key(app, "label")).set_value("Bestand neu").run()
    app.number_input(key=widget_key(app, "price")).set_value(25.0).run()
    save(app)
    (tariff,) = saved(data_dir)
    assert (tariff["id"], tariff["label"], tariff["fix_cent_kwh"]) == (
        "user_bestand",
        "Bestand neu",
        25.0,
    )


# --- step 3: further costs -----------------------------------------------------------------------------------------


def test_monthly_fees_are_saved_and_zero_fees_left_out(data_dir):
    app = start()
    create_fixed_tariff(app, "Gebühren")
    step(app, 3)
    app.number_input(key=widget_key(app, "fee_monthly_fee_eur")).set_value(4.5).run()
    app.number_input(key=widget_key(app, "fee_metering_monthly_fee_eur")).set_value(
        2.0
    ).run()
    save(app)
    (tariff,) = saved(data_dir)
    assert (tariff["monthly_fee_eur"], tariff["metering_monthly_fee_eur"]) == (4.5, 2.0)
    assert "other_monthly_fee_eur" not in tariff


def test_fee_set_back_to_zero_is_removed(data_dir):
    app = start()
    create_fixed_tariff(app, "Gebühr weg")
    step(app, 3)
    app.number_input(key=widget_key(app, "fee_other_monthly_fee_eur")).set_value(
        3.0
    ).run()
    app.number_input(key=widget_key(app, "fee_other_monthly_fee_eur")).set_value(
        0.0
    ).run()
    save(app)
    assert "other_monthly_fee_eur" not in saved(data_dir)[0]


# --- step 4: advanced ----------------------------------------------------------------------------------------------


def test_all_advanced_fields_are_saved(data_dir):
    app = start()
    create_fixed_tariff(app, "Erweitert")
    step(app, 4)
    app.checkbox(key=widget_key(app, "use_floor")).check().run()
    app.number_input(key=widget_key(app, "floor")).set_value(-5.0).run()
    app.checkbox(key=widget_key(app, "use_cap")).check().run()
    app.number_input(key=widget_key(app, "cap")).set_value(60.0).run()
    app.multiselect(key=widget_key(app, "requires")).set_value(
        list(app.multiselect(key=widget_key(app, "requires")).options[:1])
    ).run()
    app.selectbox(key=widget_key(app, "holiday_mode")).select("weekday").run()
    app.text_area(key=widget_key(app, "extra_holidays")).set_value(
        "2026-12-24\n\n 2026-12-31 \n"
    ).run()
    app.checkbox(key=widget_key(app, "individual")).check().run()
    app.text_input(key=widget_key(app, "source")).set_value("Preisblatt 2026").run()
    app.text_input(key=widget_key(app, "verified")).set_value(" 2026-11-01 ").run()
    app.text_area(key=widget_key(app, "notes")).set_value("Nur Test").run()
    save(app)
    (tariff,) = saved(data_dir)
    assert (tariff["price_floor_cent_kwh"], tariff["price_cap_cent_kwh"]) == (
        -5.0,
        60.0,
    )
    assert len(tariff["requires"]) == 1
    assert tariff["holidays"] == {"treat_as": "weekday"}
    assert tariff["extra_holiday_dates"] == ["2026-12-24", "2026-12-31"]
    assert tariff["individual"] is True
    assert (tariff["source"], tariff["last_verified"], tariff["behavior_notes"]) == (
        "Preisblatt 2026",
        "2026-11-01",
        "Nur Test",
    )


def test_unchecked_limit_is_removed_again(data_dir):
    app = start()
    create_fixed_tariff(app, "Ohne Deckel")
    step(app, 4)
    app.checkbox(key=widget_key(app, "use_cap")).check().run()
    app.number_input(key=widget_key(app, "cap")).set_value(50.0).run()
    app.checkbox(key=widget_key(app, "use_cap")).uncheck().run()
    save(app)
    assert "price_cap_cent_kwh" not in saved(data_dir)[0]


@pytest.mark.parametrize("text", ["01.11.2026", "2026-13-01", "gestern"])
def test_invalid_last_verified_date_is_refused(data_dir, text):
    app = start()
    create_fixed_tariff(app, "Datum")
    step(app, 4)
    app.text_input(key=widget_key(app, "verified")).set_value(text).run()
    expect_refused(app, data_dir, "last checked")


@pytest.mark.parametrize("text", ["24.12.2026", "2026-02-30", "2026-12-24, 2026-12-31"])
def test_invalid_extra_holiday_date_is_refused(data_dir, text):
    app = start()
    create_fixed_tariff(app, "Feiertag")
    step(app, 4)
    app.text_area(key=widget_key(app, "extra_holidays")).set_value(text).run()
    expect_refused(app, data_dir, "extra holidays")


def test_floor_above_cap_is_refused(data_dir):
    app = start()
    create_fixed_tariff(app, "Verdreht")
    step(app, 4)
    app.checkbox(key=widget_key(app, "use_floor")).check().run()
    app.number_input(key=widget_key(app, "floor")).set_value(50.0).run()
    app.checkbox(key=widget_key(app, "use_cap")).check().run()
    app.number_input(key=widget_key(app, "cap")).set_value(10.0).run()
    assert not app.exception
    assert app.error, "a floor above the cap must be reported"
    assert not has_save(app)


def test_language_switch_keeps_the_advanced_values(data_dir):
    app = start("en")
    create_fixed_tariff(app, "Sprachwechsel")
    step(app, 4)
    app.text_input(key=widget_key(app, "source")).set_value("Quelle").run()
    app.checkbox(key=widget_key(app, "individual")).check().run()
    app.sidebar.selectbox(key="ui.lang").select("de").run()
    assert app.text_input(key=widget_key(app, "source")).value == "Quelle"
    assert app.checkbox(key=widget_key(app, "individual")).value is True


# --- step 2: rule rows ---------------------------------------------------------------------------------------------


def add_row(app: AppTest) -> None:
    app.button(key=widget_key(app, "rules") + ".add").click().run()


def test_new_rule_row_starts_with_08_to_20_and_is_saved(data_dir):
    app = start()
    create_fixed_tariff(app, "Fenster")
    step(app, 2)
    add_row(app)
    (label_key,) = rule_keys(app, "label")
    app.text_input(key=label_key).set_value("Tag").run()
    (value_key,) = rule_keys(app, "value.absolute_cent")
    app.number_input(key=value_key).set_value(35.0).run()
    save(app)
    (rule,) = saved(data_dir)[0]["rules"]
    assert rule["time"] == {"from": "08:00", "to": "20:00"}
    assert (rule["id"], rule["label"], rule["effect"]) == (
        "tag",
        "Tag",
        {"mode": "absolute_cent", "value": 35.0},
    )


def test_all_day_rule_with_days_and_months(data_dir):
    app = start()
    app.sidebar.selectbox(key="house.land").select(
        "DE"
    ).run()  # land and region so weekday rules can resolve holidays
    app.sidebar.selectbox(key="house.region.DE").select("BY").run()
    create_fixed_tariff(app, "Winter WE")
    step(app, 2)
    add_row(app)
    app.checkbox(key=rule_keys(app, "all")[0]).check().run()
    assert rule_keys(app, "from") == []  # no time inputs for an all-day row
    app.multiselect(key=rule_keys(app, "days")[0]).set_value(["sat", "sun"]).run()
    app.multiselect(key=rule_keys(app, "months")[0]).set_value([12, 1, 2]).run()
    app.text_input(key=rule_keys(app, "label")[0]).set_value("Winterwochenende").run()
    save(app)
    (rule,) = saved(data_dir)[0]["rules"]
    assert "time" not in rule
    assert (rule["weekdays"], rule["months"]) == ("weekend", [1, 2, 12])


def test_all_twelve_months_mean_no_month_filter(data_dir):
    app = start()
    create_fixed_tariff(app, "Ganzjahr")
    step(app, 2)
    add_row(app)
    app.multiselect(key=rule_keys(app, "months")[0]).set_value(list(range(1, 13))).run()
    save(app)
    assert "months" not in saved(data_dir)[0]["rules"][0]


def test_rule_times_are_saved(data_dir):
    from datetime import time

    app = start()
    create_fixed_tariff(app, "Nacht")
    step(app, 2)
    add_row(app)
    app.time_input(key=rule_keys(app, "from")[0]).set_value(time(22, 0)).run()
    app.time_input(key=rule_keys(app, "to")[0]).set_value(time(6, 0)).run()
    save(app)
    assert saved(data_dir)[0]["rules"][0]["time"] == {"from": "22:00", "to": "06:00"}


def test_rule_with_equal_start_and_end_is_reported_or_saved_as_all_day(data_dir):
    from datetime import time

    app = start()
    create_fixed_tariff(app, "Null")
    step(app, 2)
    add_row(app)
    app.time_input(key=rule_keys(app, "from")[0]).set_value(time(8, 0)).run()
    app.time_input(key=rule_keys(app, "to")[0]).set_value(time(8, 0)).run()
    assert not app.exception
    assert app.error, (
        "a window from 08:00 to 08:00 is empty (or 24 h) and must be reported"
    )


def test_mode_change_clamps_the_value_into_the_new_bounds(data_dir):
    app = start()
    create_fixed_tariff(app, "Modus")
    step(app, 2)
    add_row(app)
    app.selectbox(key=rule_keys(app, "mode")[0]).select("add_cent").run()
    app.number_input(key=rule_keys(app, "value.add_cent")[0]).set_value(-4.0).run()
    app.selectbox(key=rule_keys(app, "mode")[0]).select("percent_off").run()
    assert not app.exception
    box = app.number_input(key=rule_keys(app, "value.percent_off")[0])
    assert (box.min, box.max, box.value) == (0.0, 100.0, 0.0)
    box.set_value(25.0).run()
    save(app)
    assert saved(data_dir)[0]["rules"][0]["effect"] == {
        "mode": "percent_off",
        "value": 25.0,
    }


def test_rule_rows_can_be_moved_up_and_deleted(data_dir):
    app = start()
    create_fixed_tariff(app, "Reihen")
    step(app, 2)
    for name in ("A", "B", "C"):
        add_row(app)
        app.text_input(key=rule_keys(app, "label")[-1]).set_value(name).run()
    assert app.button(key=rule_keys(app, "up")[0]).disabled
    assert app.button(key=rule_keys(app, "down")[-1]).disabled
    app.button(key=rule_keys(app, "up")[2]).click().run()
    assert [app.text_input(key=key).value for key in rule_keys(app, "label")] == [
        "A",
        "C",
        "B",
    ]
    app.button(key=rule_keys(app, "del")[0]).click().run()
    assert [app.text_input(key=key).value for key in rule_keys(app, "label")] == [
        "C",
        "B",
    ]
    save(app)
    assert [rule["label"] for rule in saved(data_dir)[0]["rules"]] == ["C", "B"]


def test_rule_rows_with_the_same_label_get_unique_ids(data_dir):
    app = start()
    create_fixed_tariff(app, "Gleich")
    step(app, 2)
    for _ in range(2):
        add_row(app)
        app.text_input(key=rule_keys(app, "label")[-1]).set_value("Spitze").run()
    save(app)
    assert [rule["id"] for rule in saved(data_dir)[0]["rules"]] == [
        "spitze",
        "spitze_2",
    ]


def test_language_switch_keeps_the_rule_rows(data_dir):
    app = start("en")
    create_fixed_tariff(app, "Regeln")
    step(app, 2)
    add_row(app)
    app.text_input(key=rule_keys(app, "label")[0]).set_value("Mittag").run()
    app.multiselect(key=rule_keys(app, "days")[0]).set_value(["mon"]).run()
    app.sidebar.selectbox(key="ui.lang").select("de").run()
    assert app.text_input(key=rule_keys(app, "label")[0]).value == "Mittag"
    assert app.multiselect(key=rule_keys(app, "days")[0]).value == ["mon"]


def test_new_tariff_after_rules_has_no_ghost_rows(data_dir):
    app = start()
    create_fixed_tariff(app, "Alt")
    step(app, 2)
    add_row(app)
    save(app)
    app.button(key="new.import").click().run()
    step(app, 1)
    assert app.text_input(key=widget_key(app, "label")).value == ""
    step(app, 2)
    assert rule_keys(app, "label") == []


@pytest.mark.xfail(
    strict=True,
    reason="found by this suite: the step radio keeps its widget value, adopt() resets only state",
)
def test_new_tariff_starts_at_step_one(data_dir):
    app = start()
    create_fixed_tariff(app, "Alt")
    save(app)
    step(app, 4)
    app.button(key="new.import").click().run()
    assert app.radio(key="ui.step_radio").value == 1
    assert [box.key for box in app.text_input if box.key == widget_key(app, "label")]


# --- leaving and deleting ------------------------------------------------------------------------------------------


def test_unsaved_edit_asks_before_a_new_tariff_and_cancel_keeps_it(data_dir):
    app = start()
    create_fixed_tariff(app, "Offen")
    save(app)
    app.number_input(key=widget_key(app, "price")).set_value(33.0).run()
    app.button(key="new.export").click().run()
    assert any("Offen" in item.value for item in app.warning)
    app.button(key="leave.cancel").click().run()
    assert app.number_input(key=widget_key(app, "price")).value == 33.0
    app.button(key="new.export").click().run()
    app.button(key="leave.save").click().run()
    assert not app.exception
    assert saved(data_dir)[0]["fix_cent_kwh"] == 33.0
    assert (
        app.text_input(key=widget_key(app, "label")).value == ""
    )  # the new export tariff is open


def test_unsaved_invalid_edit_cannot_be_saved_from_the_prompt(data_dir):
    app = start()
    create_fixed_tariff(app, "Kaputt")
    save(app)
    step(app, 4)
    app.text_input(key=widget_key(app, "verified")).set_value("kaputt").run()
    app.button(key="new.import").click().run()
    assert app.button(key="leave.save").disabled
    app.button(key="leave.discard").click().run()
    assert saved(data_dir)[0].get("last_verified") is None


def test_own_tariff_is_deleted_from_the_overview(data_dir):
    app = start()
    create_fixed_tariff(app, "Weg damit")
    save(app)
    create_fixed_tariff(app, "Bleibt")
    save(app)
    show_view(app, "overview")
    select_keys(app, "import", ["own:user_weg_damit"])
    run_action(app, "import", "delete")
    if [b for b in app.button if b.key == "delete.confirm"]:
        app.button(key="delete.confirm").click().run()
    assert not app.exception
    assert [tariff["id"] for tariff in saved(data_dir)] == ["user_bleibt"]
    assert labels(app, "import") == ["Bleibt"]


# --- preview tools -------------------------------------------------------------------------------------------------


def test_probe_shows_the_price_of_the_chosen_moment(data_dir):
    from datetime import time

    app = start()
    create_fixed_tariff(app, "Probe", 20.0)
    step(app, 2)
    add_row(app)
    app.number_input(key=rule_keys(app, "value.absolute_cent")[0]).set_value(40.0).run()
    app.time_input(key="ui.probe_time").set_value(time(3, 0)).run()
    night = "\n".join(block.value for block in app.code)
    app.time_input(key="ui.probe_time").set_value(time(12, 0)).run()
    noon = "\n".join(block.value for block in app.code)
    assert not app.exception
    assert night != noon  # 03:00 is outside 08:00–20:00, 12:00 inside


def test_invoice_check_compares_the_total(data_dir):
    app = start()
    create_fixed_tariff(app, "Rechnung", 30.0)
    (band,) = [box for box in app.number_input if box.key.startswith("ui.inv.")]
    band.set_value(100.0).run()
    app.number_input(key="ui.inv_total").set_value(30.0).run()
    assert not app.exception
    assert app.success  # 100 kWh × 30 ct = 30 € gross
    app.number_input(key="ui.inv_total").set_value(45.0).run()
    assert app.warning


# --- house settings and grid fee -----------------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="found by this suite: sidebar index fallback silently replaces it with the first timezone",
)
def test_unknown_timezone_in_house_file_is_reported_not_thrown(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "house.json").write_text(
        json.dumps({"land": "AT", "timezone": "Mars/Olympus"}), encoding="utf-8"
    )
    app = start()
    assert not app.exception
    create_fixed_tariff(app, "Zeitzone")
    assert not app.exception
    assert any(
        "Mars/Olympus" in item.value for item in [*app.error, *app.sidebar.error]
    )


def grid_key(app: AppTest, name: str) -> str:
    return f"grid{app.session_state['ui.grid_ver']}.{name}"


def test_grid_component_and_rule_are_saved_and_removed(data_dir):
    app = start()
    app.selectbox(key="house.grid_choice").select("user_house").run()
    app.number_input(key=grid_key(app, "base.unmetered_power")).set_value(5.0).run()
    app.button(key=grid_key(app, "component.add")).click().run()
    (label,) = [
        box
        for box in app.text_input
        if ".component." in box.key and box.key.endswith(".label")
    ]
    label.set_value("Messung").run()
    (value,) = [
        box
        for box in app.number_input
        if ".component." in box.key and ".value." in box.key
    ]
    value.set_value(0.25).run()
    app.button(key=grid_key(app, "rules") + ".add").click().run()
    (effect,) = [
        box
        for box in app.number_input
        if box.key.startswith(grid_key(app, "rules")) and "value." in box.key
    ]
    effect.set_value(2.0).run()
    app.button(key="grid.save").click().run()
    assert not app.exception
    (area,) = json.loads(
        (data_dir / "user_grid_fees.json").read_text(encoding="utf-8")
    )["areas"]
    grids = json.loads((data_dir / "user_grid_fees.json").read_text(encoding="utf-8"))
    assert len(grids["rule_sets"]["user_house"]) == 1
    components = area.get("components_cent_kwh") or area.get("components")
    assert components and components[0]["label"] == "Messung"
    (remove,) = [
        b
        for b in app.button
        if b.key and ".component." in b.key and b.key.endswith(".remove")
    ]
    remove.click().run()
    app.button(key="grid.save").click().run()
    (area,) = json.loads(
        (data_dir / "user_grid_fees.json").read_text(encoding="utf-8")
    )["areas"]
    assert not (area.get("components_cent_kwh") or area.get("components"))


def test_no_grid_fee_choice_saves_without_area(data_dir):
    app = start()
    app.selectbox(key="house.grid_choice").select("user_house").run()
    app.button(key="grid.save").click().run()
    app.selectbox(key="house.grid_choice").select("").run()
    app.button(key="grid.save").click().run()
    assert not app.exception
    house = json.loads((data_dir / "house.json").read_text(encoding="utf-8"))
    assert house.get("grid_area_id") is None


# --- import --------------------------------------------------------------------------------------------------------


def test_import_of_an_existing_id_needs_the_replace_checkbox(data_dir):
    app = start()
    create_fixed_tariff(app, "Import", 20.0)
    save(app)
    show_view(app, "overview")
    raw = {
        "id": "user_import",
        "label": "Import",
        "type": "fixed_cent",
        "supplier_id": "user_s",
        "fix_cent_kwh": 99.0,
        "vat_percent": 20,
    }
    app.text_area(key="import.text").set_value(json.dumps(raw)).run()
    assert app.warning
    assert app.button(key="import.add").disabled
    app.checkbox(key="import.replace.0").check().run()
    app.button(key="import.add").click().run()
    assert not app.exception
    assert [tariff["fix_cent_kwh"] for tariff in saved(data_dir)] == [99.0]


def test_import_of_an_invalid_tariff_names_it_and_adds_nothing(data_dir):
    app = start()
    raw = {
        "import_tariffs": [
            {
                "id": "ok",
                "type": "fixed_cent",
                "supplier_id": "s",
                "fix_cent_kwh": 10.0,
                "vat_percent": 20,
            },
            {
                "id": "bad",
                "type": "fixed_cent",
                "supplier_id": "s",
                "vat_percent": 20,
            },  # no price
        ]
    }
    app.text_area(key="import.text").set_value(json.dumps(raw)).run()
    assert not app.exception
    assert any("bad" in item.value for item in app.error)
    app.button(key="import.add").click().run()
    assert [tariff["id"] for tariff in saved(data_dir)] == ["user_ok"]


@pytest.mark.parametrize("text", ["[]", "42", '"text"', '{"tariff_format": 1}'])
def test_import_of_json_without_tariffs_is_reported(data_dir, text):
    app = start()
    app.text_area(key="import.text").set_value(text).run()
    assert not app.exception
    assert app.error or app.button(key="import.add").disabled
