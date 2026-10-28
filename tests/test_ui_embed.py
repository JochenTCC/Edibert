"""The editor embedded in a host page (``edibert.ui.embed``), tested headless with Streamlit's AppTest."""

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from edibert.editor.model import TariffDraft, validate
from edibert.editor.userstore import read_document, save_user_tariff
from edibert.tariff import EXPORT, IMPORT
from edibert.ui.config import UiConfig
from edibert.ui.embed import render_editor

PREFIX = "host.tariffs."


def host_page(
    data_dir: str,
    prefixes: list[str],
    open_tariff: list[str] | None = None,
    host: bool = True,
    guard: str | None = None,
    catalog: str | None = None,
) -> None:
    """A host page: one own widget, then the editor once per prefix (AppTest runs this as a script).

    ``guard``: warning text of the host's delete guard (``None``: no guard). Every ``on_change`` call is
    recorded in ``host.changes``.
    """
    from pathlib import Path

    import streamlit as st

    from edibert.context import PricingContext
    from edibert.ui.config import HostHouse, UiConfig
    from edibert.ui.embed import render_editor

    st.text_input("Host field", key="host.field")
    house = HostHouse(PricingContext("Europe/Vienna", "AT", "8"), None, (), "Hausprofil Test") if host else None
    request = (open_tariff[0], open_tariff[1]) if open_tariff else None
    changes = st.session_state.setdefault("host.changes", [])
    delete_guard = (lambda direction, tariff_id: f"{guard}: {direction}/{tariff_id}") if guard else None
    for prefix in prefixes:
        config = UiConfig(
            Path(data_dir), Path(catalog) if catalog else None, "de", prefix, house, delete_guard=delete_guard, on_change=lambda *call: changes.append(call)
        )
        render_editor(config, open_tariff=request)


def start(
    data_dir: Path,
    prefixes: list[str] | None = None,
    open_tariff: list[str] | None = None,
    host: bool = True,
    guard: str | None = None,
    catalog: Path | None = None,
) -> AppTest:
    kwargs = {
        "data_dir": str(data_dir), "prefixes": prefixes or [PREFIX], "open_tariff": open_tariff, "host": host, "guard": guard,
        "catalog": str(catalog) if catalog else None,
    }  # fmt: skip
    app = AppTest.from_function(host_page, kwargs=kwargs, default_timeout=60)
    app.run()
    assert not app.exception
    return app


def widget_key(app: AppTest, name: str, prefix: str = PREFIX) -> str:
    return f"{prefix}{app.session_state[prefix + 'ui.ver']}.{name}"


def create_fixed_tariff(app: AppTest, label: str = "Mein Tarif", price: float = 30.0, prefix: str = PREFIX) -> None:
    app.button(key=f"{prefix}new.import").click().run()
    app.text_input(key=widget_key(app, "label", prefix)).set_value(label).run()
    app.number_input(key=widget_key(app, "price", prefix)).set_value(price).run()


def save(app: AppTest, prefix: str = PREFIX) -> None:
    app.button(key=f"{prefix}ui.save").click().run()


def test_every_editor_key_carries_the_prefix(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    app.radio(key=f"{PREFIX}ui.step_radio").set_value(2).run()
    app.button(key=widget_key(app, "tpl.night")).click().run()
    save(app)
    assert not app.exception
    foreign = [key for key in app.session_state.keys() if not key.startswith((PREFIX, "host.field", "host.changes"))]  # noqa: SIM118 (AppTest state has no __iter__)
    assert foreign == []


def test_an_empty_prefix_is_refused(tmp_path):
    with pytest.raises(ValueError, match="key_prefix"):
        render_editor(UiConfig(tmp_path, None, "de"))


def test_two_embeds_do_not_share_state(tmp_path):
    app = start(tmp_path, prefixes=["a.", "b."])
    create_fixed_tariff(app, "Nur A", prefix="a.")
    assert app.session_state["a.ui.draft"] is not None
    assert app.session_state["b.ui.draft"] is None
    assert app.session_state["a.ui.ver"] != app.session_state["b.ui.ver"]


def test_host_house_is_read_only_and_no_house_file_is_written(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    save(app)
    captions = [caption.value for caption in app.caption]
    assert "Hausprofil Test" in captions
    assert any("Europe/Vienna" in c and "8 – Vorarlberg" in c for c in captions)
    assert "Netzentgelt: keines." in captions
    assert not [b for b in app.button if b.key == f"{PREFIX}house.save"]
    assert not (tmp_path / "house.json").exists()


def test_create_and_save_writes_the_user_file_and_shows_the_notice(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    save(app)
    saved = json.loads((tmp_path / "user_tariffs.json").read_text(encoding="utf-8"))
    assert saved["tariff_format"] == 1
    (tariff,) = saved["import_tariffs"]
    assert (tariff["id"], tariff["fix_cent_kwh"]) == ("user_mein_tarif", 30.0)
    assert any("user_mein_tarif" in message.value for message in app.success)  # visible after st.rerun()
    app.run()
    assert not app.success  # a notice is shown once


def test_rejected_input_leaves_the_file_unchanged(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    save(app)
    before = (tmp_path / "user_tariffs.json").read_bytes()
    app.button(key=f"{PREFIX}new.import").click().run()  # no name yet
    assert any("Name" in error.value for error in app.error)
    assert not [b for b in app.button if b.key == f"{PREFIX}ui.save"]
    assert (tmp_path / "user_tariffs.json").read_bytes() == before


def _saved_tariff(data_dir: Path, label: str = "Gespeichert", price: float = 25.0) -> str:
    draft = TariffDraft(direction=IMPORT, label=label, price_cent=price)
    validation = validate(draft, set())
    assert validation.raw is not None
    save_user_tariff(data_dir / "user_tariffs.json", validation.raw, IMPORT)
    return validation.raw["id"]


def test_open_tariff_opens_it_once_and_keeps_the_edits(tmp_path):
    tariff_id = _saved_tariff(tmp_path)
    app = start(tmp_path, open_tariff=[IMPORT, tariff_id])
    label = app.text_input(key=widget_key(app, "label"))
    assert label.value == "Gespeichert"
    label.set_value("Geändert").run()
    app.run()  # the same request on a later rerun does not reopen the saved version
    assert app.text_input(key=widget_key(app, "label")).value == "Geändert"


def test_unknown_open_tariff_is_shown_as_an_error(tmp_path):
    app = start(tmp_path, open_tariff=[IMPORT, "user_gibt_es_nicht"])
    assert any("user_gibt_es_nicht" in error.value for error in app.error)
    assert app.session_state[PREFIX + "ui.draft"] is None


def test_without_host_house_the_editor_keeps_its_own_house_settings(tmp_path):
    app = start(tmp_path, host=False)
    app.selectbox(key=f"{PREFIX}house.land").select("DE").run()
    app.button(key=f"{PREFIX}house.save").click().run()
    house = json.loads((tmp_path / "house.json").read_text(encoding="utf-8"))
    assert house["land"] == "DE"


def test_next_month_rate_of_a_monthly_table_is_written_to_the_user_file(tmp_path):
    """TE4, file side: the rate table is a ``st.data_editor`` that AppTest cannot drive, so the save path
    is checked at model level: open a saved table tariff, add the next month, save."""
    path = tmp_path / "user_tariffs.json"
    raw = {"id": "user_table", "label": "Table", "type": "monthly_table", "supplier_id": "user_s",
           "monthly_rates": [{"year": 2026, "month": 10, "tariff_cent_kwh": 12.0}], "vat_percent": 20}  # fmt: skip
    save_user_tariff(path, raw, IMPORT)
    draft = TariffDraft.from_raw(read_document(path)["import_tariffs"][0], IMPORT)
    draft.monthly_rates = [*draft.monthly_rates, (2026, 11, 13.5)]
    validation = validate(draft, {"user_table"})
    assert validation.raw is not None
    save_user_tariff(path, validation.raw, IMPORT)
    (saved,) = read_document(path)["import_tariffs"]
    assert {"year": 2026, "month": 11, "tariff_cent_kwh": 13.5} in saved["monthly_rates"]


def preview_page(language: str) -> None:
    from edibert.context import PricingContext
    from edibert.tariff import IMPORT, parse_tariff
    from edibert.ui.config import HostHouse
    from edibert.ui.embed import render_preview

    raw = {"id": "user_x", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0, "vat_percent": 20}
    house = HostHouse(PricingContext("Europe/Vienna", "AT", "8"), None)
    render_preview(parse_tariff(raw, IMPORT), house, language=language, key_prefix="host.preview.")


def test_render_preview_draws_the_curves_for_the_host(tmp_path):
    app = AppTest.from_function(preview_page, kwargs={"language": "de"}, default_timeout=60)
    app.run()
    assert not app.exception
    assert app.get("vega_lite_chart")
    assert all(key.startswith("host.preview.") for key in app.session_state.keys())  # noqa: SIM118 (AppTest state has no __iter__)



def test_new_tariff_starts_with_the_land_of_the_host_house_and_saves_it(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    land = app.selectbox(key=widget_key(app, "land"))
    assert land.value == "AT"  # visible start value from the host house
    land.select("DE").run()
    save(app)
    (tariff,) = json.loads((tmp_path / "user_tariffs.json").read_text(encoding="utf-8"))["import_tariffs"]
    assert tariff["land"] == "DE"


def test_land_can_be_left_open(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    app.selectbox(key=widget_key(app, "land")).select("").run()
    save(app)
    (tariff,) = json.loads((tmp_path / "user_tariffs.json").read_text(encoding="utf-8"))["import_tariffs"]
    assert "land" not in tariff


def _user_ids(data_dir: Path) -> list[str]:
    return [raw["id"] for raw in read_document(data_dir / "user_tariffs.json")["import_tariffs"]]


def test_save_reports_the_change_to_the_host(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    save(app)
    assert app.session_state["host.changes"] == [("save", IMPORT, "user_mein_tarif")]


def test_without_a_guard_warning_delete_is_immediate_and_reported(tmp_path):
    tariff_id = _saved_tariff(tmp_path)
    app = start(tmp_path, open_tariff=[IMPORT, tariff_id])
    app.button(key=f"{PREFIX}delete").click().run()
    assert _user_ids(tmp_path) == []
    assert app.session_state["host.changes"] == [("delete", IMPORT, tariff_id)]


def test_guard_warning_asks_before_deleting(tmp_path):
    tariff_id = _saved_tariff(tmp_path)
    app = start(tmp_path, open_tariff=[IMPORT, tariff_id], guard="Wird verwendet")
    app.button(key=f"{PREFIX}delete").click().run()
    assert _user_ids(tmp_path) == [tariff_id]
    assert [w.value for w in app.warning] == [f"Wird verwendet: {IMPORT}/{tariff_id}"]
    app.button(key=f"{PREFIX}delete.cancel").click().run()
    assert _user_ids(tmp_path) == [tariff_id]
    assert not app.warning
    app.button(key=f"{PREFIX}delete").click().run()
    app.button(key=f"{PREFIX}delete.confirm").click().run()
    assert _user_ids(tmp_path) == []
    assert app.session_state["host.changes"] == [("delete", IMPORT, tariff_id)]
    assert app.session_state[PREFIX + "ui.draft"] is None


def _catalog(tmp_path: Path) -> Path:
    def entry(tariff_id: str, label: str, tariff_type: str = "fixed_cent", land: str = "AT", **extra) -> dict:
        return {"id": tariff_id, "label": label, "type": tariff_type, "land": land, "supplier_id": "demo", "vat_percent": 20, **extra}

    document = {
        "tariff_format": 1,
        "import_tariffs": [
            entry("at_zeta", "Zeta", fix_cent_kwh=12.0),
            entry("at_wien", "Nur Wien", regions=["9"], fix_cent_kwh=11.0),
            entry("de_delta", "Delta", land="DE", fix_cent_kwh=30.0),
            entry("at_beta", "Beta", "spot_hourly", settlement_mtu="60min"),
        ],
        "export_tariffs": [entry("at_alpha", "Alpha", "spot_hourly", settlement_mtu="15min")],
    }
    path = tmp_path / "tariffs.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def unsaved_marked(app: AppTest) -> bool:
    return any("Nicht gespeichert" in caption.value for caption in app.caption)


def leave_prompt_shown(app: AppTest) -> bool:
    return any(b.key == f"{PREFIX}leave.discard" for b in app.button)


def test_copy_list_starts_with_the_house_land_and_region_imports_first(tmp_path):
    app = start(tmp_path / "data", catalog=_catalog(tmp_path))
    assert app.selectbox(key=f"{PREFIX}copy.land.AT").value == "AT"
    pick = app.selectbox(key=f"{PREFIX}copy.pick.AT.None.None")
    # "Nur Wien" is offered in another federal state than the house (8), "Delta" in another land
    assert pick.options == ["Bezug: Beta · stündlich", "Bezug: Zeta", "Einspeisung: Alpha · viertelstündlich"]


def test_direction_filter_narrows_the_type_options(tmp_path):
    app = start(tmp_path / "data", catalog=_catalog(tmp_path))
    app.selectbox(key=f"{PREFIX}copy.direction").select(EXPORT).run()
    assert app.selectbox(key=f"{PREFIX}copy.type.AT.export").options == ["Alle", "Börsenpreis + Aufschlag · viertelstündlich"]
    app.selectbox(key=f"{PREFIX}copy.land.AT").select("").run()
    app.selectbox(key=f"{PREFIX}copy.direction").select(IMPORT).run()
    app.selectbox(key=f"{PREFIX}copy.type..import").select("fixed").run()
    assert app.selectbox(key=f"{PREFIX}copy.pick.None.import.fixed").options == ["Bezug: Delta", "Bezug: Zeta"]


def test_catalog_copy_is_unsaved_and_asks_before_it_is_left(tmp_path):
    app = start(tmp_path / "data", catalog=_catalog(tmp_path))
    app.button(key=f"{PREFIX}copy.go").click().run()
    assert app.text_input(key=widget_key(app, "label")).value == "Beta (Kopie)"
    assert unsaved_marked(app)
    app.button(key=f"{PREFIX}new.import").click().run()
    assert leave_prompt_shown(app)
    assert app.text_input(key=widget_key(app, "label")).value == "Beta (Kopie)"
    app.button(key=f"{PREFIX}leave.cancel").click().run()
    assert not leave_prompt_shown(app)
    app.button(key=f"{PREFIX}new.import").click().run()
    app.button(key=f"{PREFIX}leave.discard").click().run()
    assert app.text_input(key=widget_key(app, "label")).value == ""
    assert not unsaved_marked(app)
    assert not (tmp_path / "data" / "user_tariffs.json").exists()


def test_save_in_the_prompt_writes_the_draft_and_then_leaves(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    assert unsaved_marked(app)
    app.button(key=f"{PREFIX}new.export").click().run()
    app.button(key=f"{PREFIX}leave.save").click().run()
    (tariff,) = read_document(tmp_path / "user_tariffs.json")["import_tariffs"]
    assert tariff["id"] == "user_mein_tarif"
    assert app.session_state[PREFIX + "ui.draft"].direction == EXPORT
    assert ("save", IMPORT, "user_mein_tarif") in app.session_state["host.changes"]


def test_an_invalid_draft_cannot_be_saved_from_the_prompt(tmp_path):
    app = start(tmp_path)
    app.button(key=f"{PREFIX}new.import").click().run()
    app.number_input(key=widget_key(app, "price")).set_value(20.0).run()  # changed, but no name
    app.button(key=f"{PREFIX}new.export").click().run()
    assert app.button(key=f"{PREFIX}leave.save").disabled


def test_saved_or_opened_tariff_is_left_without_asking(tmp_path):
    tariff_id = _saved_tariff(tmp_path)
    app = start(tmp_path, open_tariff=[IMPORT, tariff_id])
    app.run()
    assert not unsaved_marked(app)
    create_fixed_tariff(app)  # new tariff: leaves the opened one at once
    assert not leave_prompt_shown(app)
    save(app)
    assert not unsaved_marked(app)
    app.button(key=f"{PREFIX}open.import.{tariff_id}").click().run()
    assert not leave_prompt_shown(app)
    assert app.text_input(key=widget_key(app, "label")).value == "Gespeichert"


def test_regions_of_a_tariff_are_saved(tmp_path):
    app = start(tmp_path)
    create_fixed_tariff(app)
    app.multiselect(key=widget_key(app, "regions.AT")).select("8").run()
    save(app)
    (tariff,) = read_document(tmp_path / "user_tariffs.json")["import_tariffs"]
    assert tariff["regions"] == ["8"]


def test_market_tariff_shows_its_settlement_interval(tmp_path):
    raw = {"id": "user_spot", "label": "Spot", "type": "spot_hourly", "supplier_id": "user_s", "settlement_mtu": "60min", "vat_percent": 20}
    save_user_tariff(tmp_path / "user_tariffs.json", raw, IMPORT)
    app = start(tmp_path, open_tariff=[IMPORT, "user_spot"])
    assert app.button(key=f"{PREFIX}open.import.user_spot").label == "Bezug: Spot · stündlich"
    assert any(caption.value == "Abrechnung: stündlich" for caption in app.caption)


def test_an_unsaved_catalog_copy_offers_no_delete(tmp_path):
    app = start(tmp_path / "data", catalog=_catalog(tmp_path))
    app.button(key=f"{PREFIX}copy.go").click().run()
    assert not [b for b in app.button if b.key == f"{PREFIX}delete"]
    save(app)
    assert [b for b in app.button if b.key == f"{PREFIX}delete"]
