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
    app.button(key="new.import").click().run()
    app.text_input(key=widget_key(app, "label")).set_value(label).run()
    app.number_input(key=widget_key(app, "price")).set_value(price).run()


def test_start_page_in_both_languages(data_dir):
    english = start("en")
    assert any(item.value.startswith("Create a new tariff") for item in english.info)
    german = start("de")
    assert any(item.value.startswith("Lege oben einen neuen Tarif an") for item in german.info)
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
    listed = app.button(key="open.import.user_mein_tarif")  # listed under "My tariffs"
    assert listed.label == "Purchase: Mein Tarif"


def test_invalid_input_shows_a_translated_error_and_no_save_button(data_dir):
    app = start("de")
    app.button(key="new.import").click().run()
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


def test_grid_fee_is_entered_in_the_main_area_and_saved(data_dir):
    app = start("en")
    assert not [box for box in app.sidebar.selectbox if box.key == "house.grid_choice"]
    assert any("No catalog grid area matches AT" in item.value for item in app.info)  # no catalog: own values only
    app.selectbox(key="house.grid_choice").select("user_house").run()
    grid_base = app.number_input(key=f"grid{app.session_state['ui.grid_ver']}.base.unmetered_power")
    assert grid_base.format == "%.3f"
    grid_base.set_value(4.963).run()
    app.button(key=f"grid{app.session_state['ui.grid_ver']}.fixed.add").click().run()
    fixed = [box for box in app.number_input if box.key.endswith(".value.unmetered_power") and ".fixed." in box.key]
    fixed[0].set_value(54.0).run()
    app.button(key="grid.save").click().run()
    assert not app.exception
    house = json.loads((data_dir / "house.json").read_text(encoding="utf-8"))
    assert house["grid_area_id"] == "user_house"
    assert "grid_enabled" not in house
    grids = json.loads((data_dir / "user_grid_fees.json").read_text(encoding="utf-8"))
    (area,) = grids["areas"]
    assert area["base_cent_kwh"] == {"unmetered_power": 4.963, "metered_power": 4.963}
    assert area["fixed_eur_year"][0]["eur_year"] == {"unmetered_power": 54.0, "metered_power": 54.0}


def test_cent_amounts_keep_three_decimals(data_dir):
    app = start()
    create_fixed_tariff(app, price=12.205)
    assert app.number_input(key=widget_key(app, "price")).format == "%.3f"
    app.button(key="ui.save").click().run()
    saved = json.loads((data_dir / "user_tariffs.json").read_text(encoding="utf-8"))
    assert saved["import_tariffs"][0]["fix_cent_kwh"] == 12.205


def test_import_pasted_tariff(data_dir):
    app = start("en")
    raw = {"id": "my day night", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0, "vat_percent": 20}
    app.text_area(key="import.text").set_value(json.dumps(raw)).run()
    assert any("renamed" in info.value for info in app.info)
    app.button(key="import.add").click().run()
    saved = json.loads((data_dir / "user_tariffs.json").read_text(encoding="utf-8"))
    assert [t["id"] for t in saved["import_tariffs"]] == ["user_my_day_night"]


def test_import_of_broken_json_is_reported(data_dir):
    app = start("de")
    app.text_area(key="import.text").set_value("{ nope").run()
    assert not app.exception
    assert any("JSON" in error.value for error in app.error)


def test_copy_a_catalog_tariff(data_dir, tmp_path, monkeypatch):
    catalog = tmp_path / "tariffs.json"
    catalog.write_text(
        json.dumps({"tariff_format": 1, "import_tariffs": [{"id": "at_demo", "label": "Demo", "type": "fixed_cent", "supplier_id": "demo", "fix_cent_kwh": 12.0, "vat_percent": 20}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_CATALOG, str(catalog))
    app = start("en")
    app.button(key="copy.go").click().run()
    assert not app.exception
    assert app.text_input(key=widget_key(app, "label")).value == "Demo (copy)"


def test_spot_tariff_preview_and_invoice_check(data_dir):
    app = start("en")
    app.button(key="new.import").click().run()
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
    app.button(key="copy.go").click().run()
    assert not app.exception
    month = f"{today.year}-{today.month:02d}"
    assert any(month in warning.value and "prior_year" in warning.value for warning in app.warning)


def test_new_tariff_starts_with_the_land_of_the_house_settings(data_dir):
    app = start("en")
    app.sidebar.selectbox(key="house.land").select("CH").run()
    create_fixed_tariff(app)
    assert app.selectbox(key=widget_key(app, "land")).value == "CH"


def test_package_import_is_offered_in_the_standalone_sidebar(data_dir, tmp_path, monkeypatch):
    app = start()
    labels = [item.label for item in app.sidebar.expander]
    assert "Import catalog package" in labels
    assert "No catalog configured. Start with --catalog FILE." in [item.value for item in app.sidebar.caption]
    catalog = tmp_path / "tariffs.json"
    catalog.write_text(json.dumps({"tariff_format": 1, "import_tariffs": [], "export_tariffs": []}), encoding="utf-8")
    monkeypatch.setenv(ENV_CATALOG, str(catalog))
    with_catalog = start()
    captions = [item.value for item in with_catalog.sidebar.caption]
    assert "A signed package replaces the catalog files. Your own tariffs stay unchanged." in captions


def test_catalog_grid_area_is_offered_by_region_and_copied_as_own_values(data_dir, tmp_path, monkeypatch):
    from test_grid_areas import DOC

    catalog = tmp_path / "catalog" / "tariffs.json"
    catalog.parent.mkdir()
    catalog.write_text(json.dumps({"tariff_format": 1, "import_tariffs": [], "export_tariffs": []}), encoding="utf-8")
    (catalog.parent / "grid_fees.json").write_text(json.dumps(DOC), encoding="utf-8")
    monkeypatch.setenv(ENV_CATALOG, str(catalog))
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "house.json").write_text(json.dumps({"land": "AT", "region": "8"}), encoding="utf-8")
    app = start("en")
    choice = app.selectbox(key="house.grid_choice")
    assert choice.options[1:] == ["Q-Land (AT-Q)", "Own values"]
    choice.select("AT-Q").run()
    assert any("Fixed amounts in total: 70" in block.value for block in app.code)
    app.button(key="grid.save").click().run()
    assert json.loads((data_dir / "house.json").read_text(encoding="utf-8"))["grid_area_id"] == "AT-Q"
    app.button(key="grid.copy.AT-Q").click().run()
    assert app.selectbox(key="house.grid_choice").value == "user_house"
    assert any("Same values as database entry AT/grid/AT-Q" in item.value for item in app.caption)
    app.button(key="grid.save").click().run()
    assert not app.exception
    grids = json.loads((data_dir / "user_grid_fees.json").read_text(encoding="utf-8"))
    assert grids["areas"][0]["db_ref"]["id"] == "AT/grid/AT-Q"
    assert grids["levy_sets"]["user_house_levies"]["fixed_eur_year"][0]["eur_year"] == 20.0


def test_old_house_grid_fee_goes_through_the_migration_gate(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "house.json").write_text(json.dumps({"land": "AT", "grid_enabled": True, "grid_base_cent": 5.0, "grid_rules": []}), encoding="utf-8")
    tariff = {"id": "user_a", "type": "fixed_cent", "supplier_id": "user_x", "land": "AT", "fix_cent_kwh": 20, "vat_percent": 20,
              "grid_monthly_fee_eur": 6.0}  # fmt: skip
    (data_dir / "user_tariffs.json").write_text(json.dumps({"tariff_format": 1, "import_tariffs": [tariff], "export_tariffs": []}), encoding="utf-8")
    app = start("en")
    assert any("old form" in item.value for item in app.error)
    app.button(key="migrate.run").click().run()
    assert not app.exception
    house = json.loads((data_dir / "house.json").read_text(encoding="utf-8"))
    assert house["grid_area_id"] == "user_house" and "grid_enabled" not in house
    grids = json.loads((data_dir / "user_grid_fees.json").read_text(encoding="utf-8"))
    assert grids["areas"][0]["fixed_eur_year"][0]["eur_year"] == 60.0
    saved = json.loads((data_dir / "user_tariffs.json").read_text(encoding="utf-8"))
    assert "grid_monthly_fee_eur" not in saved["import_tariffs"][0]
