"""Tariff-format migration (``api.plan_migration`` / ``api.migrate``): pure, documents in and out."""

import copy
import json

import pytest

from edibert import api

FIXED = {"type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0, "land": "AT"}
GRID = {
    "description": "grid catalog",
    "rule_sets": {},
    "areas": [{"id": "AT-PLAIN", "base_cent_kwh": {"unmetered_power": 5.0, "metered_power": 3.0}}],
}
HOME = api.flat_user_grid_area("user_home", 5.353, label="Home", land="AT")


def old_docs() -> dict:
    """Files as Earnie 2.7 leaves them: catalog stamped with earnie_data_model, the rest untagged."""
    return {
        "tariffs.json": {"earnie_data_model": 4, "catalog_as_of": "2026-10", "import_tariffs": [{**FIXED, "id": "at_a", "vat_percent": 20}]},
        "user_tariffs.json": {"import_tariffs": [{**FIXED, "id": "user_gross"}, {**FIXED, "id": "user_net", "prices_include_vat": False}],
                              "export_tariffs": [{"id": "user_feed", "type": "fixed", "supplier_id": "s", "k_push_cent": 7.0}]},
        "grid_fees.json": copy.deepcopy(GRID),
    }  # fmt: skip


ANSWERS = {"vat_percent:import:user_gross": 20, "vat_percent:import:user_net": 19.5, "vat_percent:export:user_feed": 0}


def load_all(tmp_path, docs: dict) -> tuple:
    """The migrated documents must load through the normal strict API."""
    for name, document in docs.items():
        (tmp_path / name).write_text(json.dumps(document), encoding="utf-8")
    tariffs = api.load_tariffs(tmp_path / "tariffs.json", tmp_path / "user_tariffs.json")
    grids = api.load_grid_fees(tmp_path / "grid_fees.json", tmp_path / "user_grid_fees.json")
    return tariffs, grids


def test_plan_lists_changes_and_questions_without_changing_anything():
    docs = old_docs()
    before = copy.deepcopy(docs)
    plan = api.plan_migration(docs, user_grid_areas=[HOME])
    assert docs == before
    assert plan.current == {"tariffs.json": None, "user_tariffs.json": None, "grid_fees.json": None}
    assert plan.to_format == api.TARIFF_FORMAT == 1
    assert plan.changed_files == ("tariffs.json", "user_tariffs.json", "grid_fees.json", "user_grid_fees.json")
    assert plan.blockers == ()
    assert plan.needed and plan.can_run
    by_id = {question.id: question for question in plan.questions}
    assert set(by_id) == set(ANSWERS)  # gross and net tariffs both need the rate
    gross = by_id["vat_percent:import:user_gross"]
    assert (gross.code, gross.file, gross.kind, gross.required, gross.default) == ("VAT_PERCENT", "user_tariffs.json", "number", True, 20.0)
    assert gross.params == {"tariff_id": "user_gross", "label": "user_gross", "direction": "import", "prices": "gross", "land": "AT"}
    assert by_id["vat_percent:import:user_net"].params["prices"] == "net"
    assert by_id["vat_percent:export:user_feed"].default is None  # no land, no prefill


def test_migrate_tags_files_swaps_the_old_key_creates_user_areas_and_writes_answers(tmp_path):
    result = api.migrate(old_docs(), ANSWERS, user_grid_areas=[HOME])
    assert result.blockers == ()
    assert result.changed_files == ("tariffs.json", "user_tariffs.json", "grid_fees.json", "user_grid_fees.json")
    docs = result.docs
    assert all(document["tariff_format"] == 1 for document in docs.values())
    assert "earnie_data_model" not in docs["tariffs.json"]
    assert docs["tariffs.json"]["catalog_as_of"] == "2026-10"  # content dates stay
    assert docs["user_grid_fees.json"] == {"tariff_format": 1, "rule_sets": {}, "areas": [HOME]}
    user = {t["id"]: t for t in docs["user_tariffs.json"]["import_tariffs"] + docs["user_tariffs.json"]["export_tariffs"]}
    assert (user["user_gross"]["vat_percent"], user["user_feed"]["vat_percent"]) == (20.0, 0.0)
    assert user["user_net"]["vat_percent"] == 19.5
    tariffs, grids = load_all(tmp_path, docs)
    assert tariffs.origin[(api.IMPORT, "user_gross")] == "user"
    assert grids.origin == {"AT-PLAIN": "catalog", "user_home": "user"}
    fee = api.resolve_grid_fee(api.parse_grid_fee_config({"area_id": "user_home"}), grids)
    assert fee.base_cent_kwh == 5.353


def test_a_second_run_changes_nothing():
    migrated = api.migrate(old_docs(), ANSWERS, user_grid_areas=[HOME]).docs
    plan = api.plan_migration(migrated, user_grid_areas=[HOME])
    assert not plan.needed
    again = api.migrate(migrated, user_grid_areas=[HOME])
    assert (again.changed_files, again.blockers, again.docs) == ((), (), migrated)


def test_the_old_key_is_removed_from_every_track_file():
    docs = {"grid_fees.json": {**GRID, "earnie_data_model": 4}}  # stamped by side effect in Earnie
    result = api.migrate(docs)
    assert result.docs["grid_fees.json"] == {"tariff_format": 1, **GRID}


def test_the_vat_rate_is_never_written_unasked():
    with pytest.raises(api.EdibertError) as err:
        api.migrate(old_docs(), {"vat_percent:import:user_gross": 20})
    assert err.value.code == api.ErrorCode.MIGRATION_ANSWER_MISSING
    assert err.value.params == {"question_id": "vat_percent:import:user_net"}


@pytest.mark.parametrize("answer", [-1, "20", True, float("nan"), None])
def test_an_invalid_vat_answer_is_rejected(answer):
    with pytest.raises(api.EdibertError) as err:
        api.migrate(old_docs(), {**ANSWERS, "vat_percent:import:user_gross": answer})
    assert err.value.code == api.ErrorCode.VALUE_INVALID


def test_standard_vat_prefill_per_country():
    assert api.STANDARD_VAT_PERCENT == {"AT": 20.0, "DE": 19.0, "CH": 8.1}
    docs = {"user_tariffs.json": {"import_tariffs": [{**FIXED, "id": f"user_{land.lower()}", "land": land} for land in ("de", "CH", "IT")]}}
    defaults = {q.params["tariff_id"]: q.default for q in api.plan_migration(docs).questions}
    assert defaults == {"user_de": 19.0, "user_ch": 8.1, "user_it": None}


def test_an_existing_user_area_with_other_values_blocks_and_changes_nothing():
    docs = {"user_grid_fees.json": {"tariff_format": 1, "areas": [api.flat_user_grid_area("user_home", 4.0)]}}
    plan = api.plan_migration(docs, user_grid_areas=[HOME])
    assert [(b.code, b.file, b.params) for b in plan.blockers] == [
        (api.ErrorCode.GRID_ID_COLLISION, "user_grid_fees.json", {"grid_id": "user_home"})
    ]
    assert not plan.can_run
    result = api.migrate(docs, user_grid_areas=[HOME])
    assert (result.changed_files, result.docs) == ((), docs)


@pytest.mark.parametrize(
    ("docs", "areas", "code", "file"),
    [
        ({"tariffs.json": {"tariff_format": 2, "import_tariffs": []}}, [], api.ErrorCode.FORMAT_UNSUPPORTED, "tariffs.json"),
        ({"tariffs.json": {"import_tariffs": [{**FIXED, "id": "at_gross"}]}}, [], api.ErrorCode.VAT_PERCENT_MISSING, "tariffs.json"),
        ({"user_tariffs.json": {"import_tariffs": [{**FIXED, "id": "mine", "vat_percent": 20}]}}, [], api.ErrorCode.ID_PREFIX_MISSING, "user_tariffs.json"),
        ({"grid_fees.json": {**GRID, "colour": 1}}, [], api.ErrorCode.TARIFF_UNKNOWN_FIELD, "grid_fees.json"),
        ({}, [api.flat_user_grid_area("home", 5.0)], api.ErrorCode.GRID_ID_PREFIX_MISSING, "user_grid_fees.json"),
        ({}, [api.flat_user_grid_area("user_home", -1.0)], api.ErrorCode.VALUE_INVALID, "user_grid_fees.json"),
    ],
)  # fmt: skip
def test_blockers_name_the_code_and_the_file(docs, areas, code, file):
    plan = api.plan_migration(docs, user_grid_areas=areas)
    assert [(blocker.code, blocker.file) for blocker in plan.blockers] == [(code, file)]
    assert plan.blockers[0].message  # English, for logs
    result = api.migrate(docs, user_grid_areas=areas)
    assert result.blockers == plan.blockers
    assert result.changed_files == ()
    assert "user_grid_fees.json" not in result.docs


def test_vat_questions_and_blockers_are_independent():
    # A user tariff without a rate is a question, not a blocker; validation fills the prefill for checking only.
    docs = {"user_tariffs.json": {"import_tariffs": [{**FIXED, "id": "user_x", "label": "Mine"}]}}
    plan = api.plan_migration(docs)
    assert plan.blockers == ()
    assert [q.params["label"] for q in plan.questions] == ["Mine"]
    assert "vat_percent" not in docs["user_tariffs.json"]["import_tariffs"][0]


def test_unknown_file_names_are_rejected():
    with pytest.raises(api.EdibertError) as err:
        api.plan_migration({"house_profiles.json": {}})
    assert err.value.code == api.ErrorCode.VALUE_INVALID


def test_missing_files_may_be_left_out_or_none():
    assert api.migrate({"tariffs.json": None}).docs == {}
    assert api.TARIFF_TRACK_FILES == ("tariffs.json", "user_tariffs.json", "grid_fees.json", "user_grid_fees.json")
