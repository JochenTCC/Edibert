"""The Streamlit editor, tested headless with Streamlit's AppTest."""

import json
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

import edibert.ui as ui_package
from edibert.ui.config import ENV_CATALOG, ENV_DATA_DIR, ENV_LANG

APP = Path(ui_package.__file__).with_name("app.py")  # not imported: importing runs the page


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path / "data"))
    monkeypatch.setenv(ENV_LANG, "en")
    monkeypatch.delenv(ENV_CATALOG, raising=False)
    return tmp_path / "data"


def start(lang: str = "en") -> AppTest:
    app = AppTest.from_file(str(APP), default_timeout=60)
    app.run()
    if lang != "en":
        app.sidebar.selectbox(key="ui.lang").select(lang).run()
    assert not app.exception
    return app


def widget_key(app: AppTest, name: str) -> str:
    return f"{app.session_state['ui.ver']}.{name}"


def create_fixed_tariff(app: AppTest, label: str = "Mein Tarif", price: float = 30.0) -> None:
    app.sidebar.button(key="new.import").click().run()
    app.text_input(key=widget_key(app, "label")).set_value(label).run()
    app.number_input(key=widget_key(app, "price")).set_value(price).run()


def test_start_page_in_both_languages(data_dir):
    english = start("en")
    assert english.info[0].value.startswith("Create a new tariff")
    german = start("de")
    assert german.info[0].value.startswith("Lege einen neuen Tarif an")
    assert german.title[0].value == "Edibert Tarif-Editor"


def test_create_and_save_a_fixed_tariff(data_dir):
    app = start()
    create_fixed_tariff(app)
    assert not app.exception
    assert not app.error
    app.button(key="ui.save").click().run()
    saved = json.loads((data_dir / "user_tariffs.json").read_text(encoding="utf-8"))
    (tariff,) = saved["import_tariffs"]
    assert (tariff["id"], tariff["type"], tariff["fix_cent_kwh"]) == ("user_mein_tarif", "fixed_cent", 30.0)
    assert any("user_mein_tarif" in message.value for message in app.success)
    listed = app.sidebar.button(key="open.import.user_mein_tarif")  # listed under "My tariffs"
    assert listed.label == "Purchase: Mein Tarif"


def test_invalid_input_shows_a_translated_error_and_no_save_button(data_dir):
    app = start("de")
    app.sidebar.button(key="new.import").click().run()
    assert app.error  # no name yet: the first coded problem is shown in German
    assert not [b for b in app.button if b.key == "ui.save"]


def test_language_switch_keeps_the_entered_values(data_dir):
    app = start("en")
    create_fixed_tariff(app, "Nachttarif Test", 31.5)
    app.sidebar.selectbox(key="ui.lang").select("de").run()
    assert app.text_input(key=widget_key(app, "label")).value == "Nachttarif Test"
    assert app.number_input(key=widget_key(app, "price")).value == 31.5
    assert app.radio(key="ui.step_radio").options[1] == "2. Zeitfenster"


def test_template_adds_rule_rows_and_changes_the_preview(data_dir):
    app = start("de")
    create_fixed_tariff(app, "Tag Nacht", 30.0)
    app.radio(key="ui.step_radio").set_value(2).run()
    app.button(key=widget_key(app, "tpl.night")).click().run()
    assert not app.exception
    labels = [field.value for field in app.text_input if field.label == "Name"]
    assert labels == ["Nachttarif"]
    app.button(key=widget_key(app, "tpl.weekend")).click().run()
    assert len([field for field in app.text_input if field.label == "Name"]) == 2
    # the order of rows can be changed; the first matching row wins
    first_down = next(b for b in app.button if b.key and b.key.endswith(".down"))
    first_down.click().run()
    assert [field.value for field in app.text_input if field.label == "Name"] == ["Wochenende", "Nachttarif"]


def test_rule_without_region_reports_a_holiday_hint_instead_of_crashing(data_dir):
    app = start("en")
    create_fixed_tariff(app)
    app.radio(key="ui.step_radio").set_value(2).run()
    app.button(key=widget_key(app, "tpl.weekend")).click().run()
    assert not app.exception
    assert any("region" in error.value.lower() for error in app.error)  # weekday rule needs a region


def test_house_region_removes_the_hint_and_is_saved(data_dir):
    app = start("en")
    create_fixed_tariff(app)
    app.radio(key="ui.step_radio").set_value(2).run()
    app.button(key=widget_key(app, "tpl.weekend")).click().run()
    app.sidebar.selectbox(key="house.land").select("DE").run()
    app.sidebar.selectbox(key="house.region.DE").select("BY").run()
    assert not app.exception
    assert not app.error
    app.sidebar.button(key="house.save").click().run()
    house = json.loads((data_dir / "house.json").read_text(encoding="utf-8"))
    assert (house["land"], house["region"]) == ("DE", "BY")


def test_import_pasted_tariff(data_dir):
    app = start("en")
    raw = {"id": "my day night", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0, "vat_percent": 20}
    app.sidebar.text_area(key="import.text").set_value(json.dumps(raw)).run()
    assert any("renamed" in info.value for info in app.sidebar.info)
    app.sidebar.button(key="import.add").click().run()
    saved = json.loads((data_dir / "user_tariffs.json").read_text(encoding="utf-8"))
    assert [t["id"] for t in saved["import_tariffs"]] == ["user_my_day_night"]


def test_import_of_broken_json_is_reported(data_dir):
    app = start("de")
    app.sidebar.text_area(key="import.text").set_value("{ nope").run()
    assert not app.exception
    assert any("JSON" in error.value for error in app.sidebar.error)


def test_copy_a_catalog_tariff(data_dir, tmp_path, monkeypatch):
    catalog = tmp_path / "tariffs.json"
    catalog.write_text(
        json.dumps({"tariff_format": 1, "import_tariffs": [{"id": "at_demo", "label": "Demo", "type": "fixed_cent", "supplier_id": "demo", "fix_cent_kwh": 12.0, "vat_percent": 20}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_CATALOG, str(catalog))
    app = start("en")
    app.sidebar.button(key="copy.go").click().run()
    assert not app.exception
    assert app.text_input(key=widget_key(app, "label")).value == "Demo (copy)"


def test_spot_tariff_preview_and_invoice_check(data_dir):
    app = start("en")
    app.sidebar.button(key="new.import").click().run()
    app.text_input(key=widget_key(app, "label")).set_value("Spot").run()
    app.radio(key=widget_key(app, "kind")).set_value("spot").run()
    app.checkbox(key=widget_key(app, "vat_included")).set_value(False).run()
    app.number_input(key=widget_key(app, "vat_percent")).set_value(20.0).run()
    assert not app.exception
    assert not app.error
    assert any("example market curve" in caption.value for caption in app.caption)
    assert app.get("vega_lite_chart")  # the price curve is drawn


def test_monthly_table_preview_shows_the_month_rate_fallback(data_dir, tmp_path, monkeypatch):
    today = date.today()
    rates = [{"year": today.year - 1, "month": m, "tariff_cent_kwh": 10.0 + m} for m in range(1, 13)]
    tariff = {"id": "at_table", "label": "Table", "type": "monthly_table", "supplier_id": "demo", "monthly_rates": rates, "vat_percent": 20}
    catalog = tmp_path / "tariffs.json"
    catalog.write_text(json.dumps({"tariff_format": 1, "import_tariffs": [tariff]}), encoding="utf-8")
    monkeypatch.setenv(ENV_CATALOG, str(catalog))
    app = start("en")
    app.sidebar.button(key="copy.go").click().run()
    assert not app.exception
    month = f"{today.year}-{today.month:02d}"
    assert any(month in warning.value and "prior_year" in warning.value for warning in app.warning)


def test_new_tariff_starts_with_the_land_of_the_house_settings(data_dir):
    app = start("en")
    app.sidebar.selectbox(key="house.land").select("CH").run()
    create_fixed_tariff(app)
    assert app.selectbox(key=widget_key(app, "land")).value == "CH"
