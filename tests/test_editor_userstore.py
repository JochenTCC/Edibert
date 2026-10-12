"""Reading, writing and importing user tariffs."""

import json

import pytest
from conftest import load_example

from edbert.editor.userstore import (
    copy_as_template,
    delete_user_tariff,
    parse_import_text,
    read_document,
    save_user_tariff,
    user_tariff_ids,
)
from edbert.errors import EdbertError, ErrorCode
from edbert.store import load_tariffs
from edbert.tariff import EXPORT, IMPORT

IMPORT_RAW = {"id": "user_a", "type": "fixed_cent", "supplier_id": "user_s", "fix_cent_kwh": 30.0}
EXPORT_RAW = {"id": "user_e", "type": "fixed", "supplier_id": "user_s", "k_push_cent": 5.0}


def test_save_replace_and_delete(tmp_path):
    path = tmp_path / "data" / "user_tariffs.json"
    save_user_tariff(path, IMPORT_RAW, IMPORT)
    save_user_tariff(path, EXPORT_RAW, EXPORT)
    save_user_tariff(path, {**IMPORT_RAW, "fix_cent_kwh": 31.0}, IMPORT)  # same ID replaces
    document = read_document(path)
    assert [t["fix_cent_kwh"] for t in document["import_tariffs"]] == [31.0]
    assert [t["id"] for t in document["export_tariffs"]] == ["user_e"]
    assert user_tariff_ids(path) == {IMPORT: {"user_a"}, EXPORT: {"user_e"}}
    assert set(load_tariffs(None, path).imports) == {"user_a"}  # the engine can read what the editor wrote
    delete_user_tariff(path, "user_a", IMPORT)
    assert read_document(path)["import_tariffs"] == []
    assert read_document(path)["export_tariffs"][0]["id"] == "user_e"


def test_invalid_tariff_is_not_written(tmp_path):
    path = tmp_path / "user_tariffs.json"
    save_user_tariff(path, IMPORT_RAW, IMPORT)
    before = path.read_text(encoding="utf-8")
    with pytest.raises(EdbertError) as err:
        save_user_tariff(path, {**IMPORT_RAW, "id": "user_b", "colour": 1}, IMPORT)
    assert err.value.code == ErrorCode.TARIFF_UNKNOWN_FIELD
    assert path.read_text(encoding="utf-8") == before


def test_missing_file_is_an_empty_document_and_broken_file_is_an_error(tmp_path):
    assert read_document(tmp_path / "none.json") == {"import_tariffs": [], "export_tariffs": []}
    broken = tmp_path / "broken.json"
    broken.write_text("{ nope", encoding="utf-8")
    with pytest.raises(EdbertError) as err:
        read_document(broken)
    assert err.value.code == ErrorCode.FILE_INVALID


def test_file_is_written_as_utf8_with_umlauts(tmp_path):
    path = tmp_path / "user_tariffs.json"
    save_user_tariff(path, {**IMPORT_RAW, "label": "Größe Ärger"}, IMPORT)
    assert "Größe Ärger" in path.read_text(encoding="utf-8")


def test_copy_as_template_gets_a_user_id_and_label():
    catalog = {"id": "at_vkw_strom_duo", "label": "VKW Strom Duo", "type": "fixed_cent", "supplier_id": "vkw", "fix_cent_kwh": 9.4}
    copy = copy_as_template(catalog, {"user_at_vkw_strom_duo"}, "(copy)")
    assert copy["id"] == "user_at_vkw_strom_duo_2"
    assert copy["label"] == "VKW Strom Duo (copy)"
    assert copy["supplier_id"] == "user_vkw"
    assert catalog["id"] == "at_vkw_strom_duo"  # the original is not changed


def test_import_single_tariff_is_renamed_and_validated():
    raw = load_example("fixed_day_night.json")
    raw["id"] = "stadtwerk day night"
    (item,) = parse_import_text(json.dumps(raw), IMPORT, {IMPORT: set(), EXPORT: set()})
    assert item.error is None
    assert (item.renamed_from, item.raw["id"]) == ("stadtwerk day night", "user_stadtwerk_day_night")
    assert not item.collides


def test_import_flags_collisions_and_errors():
    raw = {**IMPORT_RAW}
    (item,) = parse_import_text(json.dumps(raw), IMPORT, {IMPORT: {"user_a"}, EXPORT: set()})
    assert item.collides
    (bad,) = parse_import_text(json.dumps({**raw, "colour": 1}), IMPORT, {IMPORT: set(), EXPORT: set()})
    assert bad.error is not None
    assert bad.error.code == ErrorCode.TARIFF_UNKNOWN_FIELD
    assert bad.tariff is None


def test_import_document_with_both_directions_and_export_detection():
    document = {"import_tariffs": [IMPORT_RAW], "export_tariffs": [EXPORT_RAW]}
    items = parse_import_text(json.dumps(document), IMPORT, {IMPORT: set(), EXPORT: set()})
    assert [(i.direction, i.raw["id"]) for i in items] == [(IMPORT, "user_a"), (EXPORT, "user_e")]
    (single,) = parse_import_text(json.dumps(EXPORT_RAW), IMPORT, {IMPORT: set(), EXPORT: set()})
    assert single.direction == EXPORT  # a fixed feed-in price can only be an export tariff


def test_import_rejects_non_json_and_unknown_root_fields():
    taken = {IMPORT: set(), EXPORT: set()}
    with pytest.raises(EdbertError) as err:
        parse_import_text("{ not json", IMPORT, taken)
    assert err.value.code == ErrorCode.FILE_INVALID
    with pytest.raises(EdbertError) as err:
        parse_import_text(json.dumps({"import_tariffs": [], "oops": 1}), IMPORT, taken)
    assert err.value.code == ErrorCode.TARIFF_UNKNOWN_FIELD
