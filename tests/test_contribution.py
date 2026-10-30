"""Sharing client (Catalog P6): whitelist payload, individual refusal, selection, transport, share section."""

import json
from pathlib import Path

import pytest

from edibert.contribution import (
    CONTRIBUTION_FORMAT,
    SendResult,
    SendStatus,
    ShareDefault,
    check_share_default,
    contribution_items,
    contribution_payload,
    initially_selected,
    payload_text,
    send_selected,
)
from edibert.editor.userstore import save_user_tariff
from edibert.errors import EdibertError, ErrorCode
from edibert.tariff import EXPORT, IMPORT, DbRef


def full_tariff(**extra) -> dict:
    return {
        "$comment": "my own note",
        "id": "user_night",
        "label": "Night Saver",
        "type": "fixed_cent",
        "supplier_id": "user_demo",
        "land": "AT",
        "regions": ["8"],
        "fix_cent_kwh": 30.0,
        "vat_percent": 20,
        "prices_include_vat": False,
        "monthly_fee_eur": 4.5,
        "notes": "call the hotline first",
        "behavior_notes": "bonus only with controlled charging",
        "source": "price sheet 2026-10",
        "last_verified": "2026-10-01",
        "holidays": {"treat_as": "sunday", "$comment": "x"},
        "rules": [
            {"id": "night", "label": "My night window", "$comment": "c", "time": {"from": "22:00", "to": "06:00", "$comment": "t"},
             "effect": {"mode": "absolute_cent", "value": 20.0}},
        ],
        **extra,
    }  # fmt: skip


def test_payload_keeps_only_whitelisted_fields():
    payload = contribution_payload(full_tariff(), IMPORT)
    assert payload["contribution_format"] == CONTRIBUTION_FORMAT
    assert payload["direction"] == IMPORT
    tariff = payload["tariff"]
    assert tariff == {
        "label": "Night Saver", "type": "fixed_cent", "supplier_id": "user_demo", "land": "AT", "regions": ["8"],
        "fix_cent_kwh": 30.0, "vat_percent": 20, "prices_include_vat": False, "monthly_fee_eur": 4.5,
        "source": "price sheet 2026-10", "last_verified": "2026-10-01", "holidays": {"treat_as": "sunday"},
        "rules": [{"id": "night", "time": {"from": "22:00", "to": "06:00"}, "effect": {"mode": "absolute_cent", "value": 20.0}}],
    }  # fmt: skip


def test_payload_never_contains_free_text_or_the_local_id():
    text = payload_text(contribution_payload(full_tariff(), IMPORT))
    for secret in ("my own note", "call the hotline", "controlled charging", "My night window", "user_night", "$comment"):
        assert secret not in text


def test_payload_does_not_change_the_stored_tariff():
    raw = full_tariff()
    before = json.dumps(raw, sort_keys=True)
    contribution_payload(raw, IMPORT)
    assert json.dumps(raw, sort_keys=True) == before


@pytest.mark.parametrize("direction", [IMPORT, EXPORT])
def test_individual_tariff_is_always_refused(direction):
    raw = {"id": "user_special", "type": "spot_hourly", "supplier_id": "user_s", "vat_percent": 20, "individual": True}
    with pytest.raises(EdibertError) as caught:
        contribution_payload(raw, direction)
    assert caught.value.code is ErrorCode.CONTRIBUTION_INDIVIDUAL
    assert caught.value.params == {"tariff_id": "user_special"}


def test_invalid_tariff_is_refused_with_its_own_code():
    raw = full_tariff(meter_number="AT0000")  # unknown field: never shared, never silently dropped
    with pytest.raises(EdibertError) as caught:
        contribution_payload(raw, IMPORT)
    assert caught.value.code is ErrorCode.TARIFF_UNKNOWN_FIELD


def test_payload_text_is_stable():
    first = payload_text(contribution_payload(full_tariff(), IMPORT))
    reordered = dict(reversed(list(full_tariff().items())))
    assert payload_text(contribution_payload(reordered, IMPORT)) == first
    assert json.loads(first)["tariff"]["label"] == "Night Saver"


def document() -> dict:
    personal = {"id": "user_personal", "label": "Personal", "type": "fixed", "supplier_id": "user_s", "k_push_cent": 8.0,
                "vat_percent": 0, "individual": True}  # fmt: skip
    return {"tariff_format": 1, "import_tariffs": [full_tariff()], "export_tariffs": [personal]}


def test_items_list_every_tariff_with_payload_or_reason():
    shared, personal = contribution_items(document())
    assert (shared.direction, shared.tariff_id, shared.label, shared.shareable) == (IMPORT, "user_night", "Night Saver", True)
    assert (personal.direction, personal.shareable) == (EXPORT, False)
    assert personal.error is not None and personal.error.code is ErrorCode.CONTRIBUTION_INDIVIDUAL


def test_start_selection_follows_the_share_default_but_never_selects_a_refused_tariff():
    shared, personal = contribution_items(document())
    assert initially_selected(shared, ShareDefault.SHARE)
    assert not initially_selected(shared, ShareDefault.OPT_IN)
    assert not initially_selected(personal, ShareDefault.SHARE)


@pytest.mark.parametrize("value", [None, True, "share", ""])
def test_share_default_has_no_implicit_value(value):
    with pytest.raises(TypeError, match="share_default"):
        check_share_default(value)


class Recorder:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.refs: list[DbRef | None] = []

    def send(self, payload, db_ref) -> SendResult:
        self.sent.append(payload_text(payload))
        self.refs.append(db_ref)
        return SendResult(SendStatus.ACCEPTED)


def test_without_a_transport_sending_is_off():
    shared, _ = contribution_items(document())
    with pytest.raises(EdibertError) as caught:
        send_selected(None, [shared])
    assert caught.value.code is ErrorCode.CONTRIBUTION_TRANSPORT_OFF


def test_transport_gets_exactly_the_previewed_payload():
    shared, _ = contribution_items(document())
    rec = Recorder()
    assert send_selected(rec, [shared]) == [SendResult(SendStatus.ACCEPTED)]
    assert rec.sent == [payload_text(contribution_payload(full_tariff(), IMPORT))]
    assert rec.refs == [None]


def test_refused_items_are_never_sent():
    _, personal = contribution_items(document())
    rec = Recorder()
    with pytest.raises(ValueError, match="user_personal"):
        send_selected(rec, [personal])
    assert rec.sent == []


# --- regressions: share without reason / without land / without based_on (Backlog-Bugfixes, 2026-10-30) ---


def test_tariff_without_land_is_refused_locally():
    """Valid locally, but the server needs the land for the database ID and rejected it without a visible reason."""
    raw = {k: v for k, v in full_tariff().items() if k not in ("land", "regions")}
    with pytest.raises(EdibertError) as caught:
        contribution_payload(raw, IMPORT)
    assert caught.value.code is ErrorCode.CONTRIBUTION_LAND_MISSING
    [item] = contribution_items({"tariff_format": 1, "import_tariffs": [raw], "export_tariffs": []})
    assert not item.shareable and item.error is not None and item.error.code is ErrorCode.CONTRIBUTION_LAND_MISSING


def test_db_ref_of_a_shared_tariff_reaches_the_transport():
    """A tariff shared before carries its db_ref, so the server makes a new version instead of a new entry."""
    ref = {"database": "free", "id": "AT/import/shared_abc", "version": "a" * 64}
    [item] = contribution_items({"tariff_format": 1, "import_tariffs": [full_tariff(db_ref=ref)], "export_tariffs": []})
    rec = Recorder()
    send_selected(rec, [item])
    assert rec.refs == [DbRef(**ref)]
    assert "db_ref" not in json.loads(rec.sent[0])["tariff"]


def test_result_message_names_each_rejected_tariff_with_its_reason():
    from edibert.i18n import Translator
    from edibert.ui.share import result_message

    shared, _ = contribution_items(document())
    other = contribution_items({"tariff_format": 1, "import_tariffs": [full_tariff(id="user_b", label="Second")], "export_tariffs": []})[0]
    t = Translator("de")
    results = [SendResult(SendStatus.REJECTED, "TARIFF_INVALID"), SendResult(SendStatus.REJECTED, "SOMETHING_NEW")]
    message, kind = result_message(t, [shared, other], results)
    assert kind == "warning"
    assert "0 angenommen" in message and "2 abgelehnt" in message
    assert "Bezug: Night Saver: abgelehnt. " + t.t("ui.share_reject.TARIFF_INVALID") in message
    assert "Bezug: Second: abgelehnt. Grund laut Server: SOMETHING_NEW." in message
    assert result_message(t, [shared], [SendResult(SendStatus.ACCEPTED)])[1] == "success"


# --- the share section in the editor (AppTest) ---

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

PREFIX = "host.tariffs."


def host_page(data_dir: str, share_default: str, with_transport: bool, reject_code: str | None) -> None:
    from pathlib import Path

    import streamlit as st

    from edibert.contribution import SendResult, SendStatus, ShareDefault, payload_text
    from edibert.ui.config import UiConfig
    from edibert.ui.embed import render_editor

    sent = st.session_state.setdefault("host.sent", [])

    class Transport:
        def send(self, payload, db_ref) -> SendResult:
            sent.append(payload_text(payload))
            return SendResult(SendStatus.REJECTED, reject_code) if reject_code else SendResult(SendStatus.ACCEPTED)

    config = UiConfig(Path(data_dir), None, "de", "host.tariffs.", contribution_transport=Transport() if with_transport else None)
    render_editor(config, share_default=ShareDefault(share_default))


def start(data_dir: Path, share_default: ShareDefault, with_transport: bool = False, reject_code: str | None = None) -> AppTest:
    save_user_tariff(data_dir / "user_tariffs.json", full_tariff(), IMPORT)
    personal = {"id": "user_personal", "label": "Personal", "type": "fixed", "supplier_id": "user_s", "k_push_cent": 8.0,
                "vat_percent": 0, "individual": True}  # fmt: skip
    save_user_tariff(data_dir / "user_tariffs.json", personal, EXPORT)
    kwargs = {"data_dir": str(data_dir), "share_default": share_default.value, "with_transport": with_transport, "reject_code": reject_code}
    app = AppTest.from_function(host_page, kwargs=kwargs, default_timeout=60)
    app.run()
    assert not app.exception
    return app


def share_box(app: AppTest):
    return app.checkbox(key=f"{PREFIX}share.import.user_night")


def test_opt_in_starts_unselected_and_shows_no_payload(tmp_path):
    app = start(tmp_path, ShareDefault.OPT_IN)
    assert share_box(app).value is False
    assert not app.code
    assert not [box for box in app.checkbox if box.key == f"{PREFIX}share.export.user_personal"]
    assert any("Personal" in caption.value and "persönlich" in caption.value for caption in app.caption)


def test_share_default_selects_and_previews_the_exact_payload(tmp_path):
    app = start(tmp_path, ShareDefault.SHARE)
    assert share_box(app).value is True
    (code,) = app.code
    assert code.value == payload_text(contribution_payload(full_tariff(), IMPORT))
    share_box(app).uncheck().run()
    assert not app.code


def test_without_transport_the_section_says_sharing_is_off_and_cannot_send(tmp_path):
    app = start(tmp_path, ShareDefault.SHARE)
    assert any("Teilen ist aus" in caption.value for caption in app.caption)
    assert app.button(key=f"{PREFIX}share.send").disabled


def test_send_delivers_the_selected_payloads_and_reports(tmp_path):
    app = start(tmp_path, ShareDefault.OPT_IN, with_transport=True)
    assert app.button(key=f"{PREFIX}share.send").disabled  # nothing selected yet
    share_box(app).check().run()
    app.button(key=f"{PREFIX}share.send").click().run()
    assert not app.exception
    assert app.session_state["host.sent"] == [payload_text(contribution_payload(full_tariff(), IMPORT))]
    assert any("1 angenommen" in message.value for message in app.success)


def test_send_shows_the_reason_of_a_rejection(tmp_path):
    app = start(tmp_path, ShareDefault.OPT_IN, with_transport=True, reject_code="VERSION_MISMATCH")
    share_box(app).check().run()
    app.button(key=f"{PREFIX}share.send").click().run()
    assert not app.exception
    assert any("Night Saver: abgelehnt" in w.value and "Preisversion" in w.value for w in app.warning)


def test_embed_without_share_default_is_refused(tmp_path):
    from edibert.ui.config import UiConfig
    from edibert.ui.embed import render_editor

    with pytest.raises(TypeError):
        render_editor(UiConfig(tmp_path, None, "de", PREFIX))  # type: ignore[call-arg]
    with pytest.raises(TypeError, match="share_default"):
        render_editor(UiConfig(tmp_path, None, "de", PREFIX), share_default="share")  # type: ignore[arg-type]


def test_standalone_editor_shares_by_default(tmp_path, monkeypatch):
    import edibert.ui as ui_package
    from edibert.ui.config import ENV_CATALOG, ENV_DATA_DIR, ENV_LANG

    monkeypatch.setenv(ENV_DATA_DIR, str(tmp_path))
    monkeypatch.setenv(ENV_LANG, "en")
    monkeypatch.delenv(ENV_CATALOG, raising=False)
    save_user_tariff(tmp_path / "user_tariffs.json", full_tariff(), IMPORT)
    app = AppTest.from_file(str(Path(ui_package.__file__).with_name("app.py")), default_timeout=60)
    app.run()
    assert not app.exception
    assert app.checkbox(key="share.import.user_night").value is True
    assert any("Sharing is off" in caption.value for caption in app.caption)
