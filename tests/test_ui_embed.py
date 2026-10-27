"""The editor embedded in a host page (``edibert.ui.embed``), tested headless with Streamlit's AppTest."""

import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from edibert.editor.model import TariffDraft, validate
from edibert.editor.userstore import read_document, save_user_tariff
from edibert.tariff import IMPORT
from edibert.ui.config import UiConfig
from edibert.ui.embed import render_editor

PREFIX = "host.tariffs."


def host_page(
    data_dir: str, prefixes: list[str], open_tariff: list[str] | None = None, host: bool = True, guard: str | None = None
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
            Path(data_dir), None, "de", prefix, house, delete_guard=delete_guard, on_change=lambda *call: changes.append(call)
        )
        render_editor(config, open_tariff=request)


def start(
    data_dir: Path, prefixes: list[str] | None = None, open_tariff: list[str] | None = None, host: bool = True, guard: str | None = None
) -> AppTest:
    kwargs = {"data_dir": str(data_dir), "prefixes": prefixes or [PREFIX], "open_tariff": open_tariff, "host": host, "guard": guard}
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
