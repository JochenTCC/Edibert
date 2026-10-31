"""Tariff database client, part 1 (Catalog P1-P5): identity and version, validity versions, db_ref,
signed packages and their import."""

import json
from datetime import UTC, date, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from edibert.catalog_import import (
    KEEP_LOCAL,
    TAKE_PACKAGE,
    apply_package_import,
    plan_package_import,
    write_catalog_pair,
)
from edibert.cli import main
from edibert.context import PricingContext
from edibert.editor.catalog import catalog_package, read_catalog
from edibert.editor.model import TariffDraft
from edibert.editor.userstore import copy_as_template
from edibert.errors import EdibertError, ErrorCode, WarningCode
from edibert.identity import (
    db_ref_for,
    differs_from_db,
    grid_area_identity,
    grid_area_version,
    tariff_identity,
    tariff_version,
)
from edibert.package import build_package, public_key_text, verify_package
from edibert.store import load_tariffs, parse_tariff_documents
from edibert.tariff import EXPORT, IMPORT, parse_tariff, price_cent

BASE = {
    "id": "at_x_fix", "label": "X Fix", "type": "fixed_cent", "supplier_id": "x", "land": "AT",
    "fix_cent_kwh": 20, "vat_percent": 20,
}  # fmt: skip
MONTHLY = {
    "id": "at_x_monthly", "type": "monthly_table", "supplier_id": "x", "land": "AT", "vat_percent": 20,
    "monthly_rates": [{"year": 2026, "month": 9, "tariff_cent_kwh": 9.0}, {"year": 2026, "month": 10, "tariff_cent_kwh": 9.5}],
}  # fmt: skip
CHECK = {"state": "checked", "checked_at": "2026-10-20", "source": "price sheet 2026-10"}
AREA = {"id": "AT-X", "label": "X", "land": "AT", "base_cent_kwh": {"unmetered_power": 8.0, "metered_power": 6.0}, "check": CHECK}
KEY_ID = "test-1"
CHECK = {"state": "checked", "checked_at": "2026-10-20", "source": "price sheet 2026-10"}
TODAY = date(2026, 10, 29)


def code_of(func, *args, **kwargs):
    with pytest.raises(EdibertError) as err:
        func(*args, **kwargs)
    return err.value.code


def tariffs_doc(imports=(BASE,), exports=(), **root):
    return {"tariff_format": 1, "import_tariffs": list(imports), "export_tariffs": list(exports), **root}


def grid_doc(*areas):
    return {"tariff_format": 1, "rule_sets": {}, "areas": list(areas or [AREA])}


@pytest.fixture(scope="module")
def signing():
    key = Ed25519PrivateKey.generate()
    return key, {KEY_ID: public_key_text(key.public_key())}


def manifest(**changes):
    base = {
        "package_id": "2026-10-a", "issued_at": "2026-10-29T08:00:00+00:00",
        "valid_until": "2026-12-31", "tariff_format": 1, "key_id": KEY_ID,
    }  # fmt: skip
    return {**base, **changes}


def checked(document):
    """A catalog document as a package carries it: every tariff with its ``check``."""
    return {
        **document,
        **{section: [{"check": CHECK, **raw} for raw in document.get(section) or []] for section in ("import_tariffs", "export_tariffs")},
    }


def make_package(signing, tariffs=None, grid=None, *, unchecked=False, **changes):
    content = tariffs or tariffs_doc()
    return build_package(content if unchecked else checked(content), grid or grid_doc(), manifest(**changes), signing[0])


# --- P1: identity and version ---------------------------------------------------------------


def test_identity_of_catalog_tariff_and_grid_area():
    assert tariff_identity(BASE, IMPORT) == "AT/import/at_x_fix"
    assert grid_area_identity(AREA) == "AT/grid/AT-X"


def test_user_entries_and_entries_without_land_have_no_identity():
    assert code_of(tariff_identity, {**BASE, "id": "user_x"}, IMPORT) == ErrorCode.DB_ID_UNAVAILABLE
    assert code_of(grid_area_identity, {**AREA, "id": "user_home"}) == ErrorCode.DB_ID_UNAVAILABLE
    no_land = {key: value for key, value in BASE.items() if key != "land"}
    assert code_of(tariff_identity, no_land, IMPORT) == ErrorCode.FIELD_MISSING


def test_version_ignores_spelling_order_and_display_fields():
    version = tariff_version(BASE, IMPORT)
    assert len(version) == 64
    respelled = {**dict(reversed(BASE.items())), "fix_cent_kwh": 20.0, "vat_percent": 20.0}
    shown = {**BASE, "label": "Other", "source": "sheet.pdf", "last_verified": "2026-10-01", "notes": "n", "$comment": "c"}
    defaults = {**BASE, "settlement_mtu": "15min", "markup_percent": 0, "prices_include_vat": True}
    assert tariff_version(respelled, IMPORT) == version
    assert tariff_version(shown, IMPORT) == version
    assert tariff_version(defaults, IMPORT) == version


def test_version_changes_with_every_price_change():
    version = tariff_version(BASE, IMPORT)
    assert tariff_version({**BASE, "fix_cent_kwh": 20.01}, IMPORT) != version
    assert tariff_version({**BASE, "vat_percent": 19}, IMPORT) != version
    assert tariff_version({**BASE, "valid_from": "2027-01-01"}, IMPORT) != version
    rule = {"id": "night", "time": {"from": "22:00", "to": "06:00"}, "effect": {"mode": "add_cent", "value": -2}}
    assert tariff_version({**BASE, "rules": [rule]}, IMPORT) != version
    moved = {**MONTHLY, "monthly_rates": [{"year": 2026, "month": 9, "tariff_cent_kwh": 9.1}, MONTHLY["monthly_rates"][1]]}
    assert tariff_version(moved, IMPORT) != tariff_version(MONTHLY, IMPORT)


def test_version_ignores_rule_ids_and_month_row_order():
    rule = {"id": "night", "label": "Night", "time": {"from": "22:00", "to": "06:00"}, "effect": {"mode": "add_cent", "value": -2}}
    renamed = {**rule, "id": "rule_1", "label": "Nacht"}
    assert tariff_version({**BASE, "rules": [rule]}, IMPORT) == tariff_version({**BASE, "rules": [renamed]}, IMPORT)
    reordered = {**MONTHLY, "monthly_rates": list(reversed(MONTHLY["monthly_rates"]))}
    assert tariff_version(reordered, IMPORT) == tariff_version(MONTHLY, IMPORT)


def test_version_ignores_fields_the_type_does_not_use():
    # The editor drops a settlement fee on a monthly export table; the price never used it (Earnie catalog case).
    export_table = {**MONTHLY, "id": "at_x_feed", "prices_include_vat": False, "vat_percent": 0}
    with_fee = {**export_table, "settlement_fee_cent_kwh": 0.6}
    assert tariff_version(with_fee, EXPORT) == tariff_version(export_table, EXPORT)
    spot = {"id": "at_x_spot", "type": "spot_hourly", "supplier_id": "x", "land": "AT", "vat_percent": 20}
    assert tariff_version({**spot, "settlement_fee_cent_kwh": 1.5}, IMPORT) != tariff_version(spot, IMPORT)


def test_version_of_invalid_entry_is_an_error():
    assert code_of(tariff_version, {**BASE, "fix_cent_kwh": "x"}, IMPORT) == ErrorCode.VALUE_INVALID


def test_grid_area_version_follows_prices_and_rule_set():
    rules = {"AT_NE7": [{"id": "SNAP", "status": "verordnet", "months": [4, 5], "effect": {"mode": "percent_off", "value": 20}}]}
    area = {**AREA, "rule_set": "AT_NE7"}
    version = grid_area_version(area, rules)
    assert grid_area_version({**area, "label": "Y", "source": "z"}, rules) == version
    assert grid_area_version({**area, "base_cent_kwh": {"unmetered_power": 8.1, "metered_power": 6.0}}, rules) != version
    changed = {"AT_NE7": [{**rules["AT_NE7"][0], "effect": {"mode": "percent_off", "value": 25}}]}
    assert grid_area_version(area, changed) != version


# --- P2: validity versions ------------------------------------------------------------------


def versions(*entries):
    return parse_tariff_documents(tariffs_doc(entries), None).imports["at_x_fix"]


def test_catalog_versions_price_each_slot_with_its_version():
    old = {**BASE, "valid_to": "2026-12-31"}
    new = {**BASE, "fix_cent_kwh": 25, "valid_from": "2027-01-01"}
    tariff = versions({**old, "valid_from": "2026-01-01"}, new)
    ctx = PricingContext("Europe/Vienna")
    assert [version.fix_cent_kwh for version in tariff.periods] == [20.0, 25.0]
    assert price_cent(tariff, datetime(2026, 12, 31, 22, 45, tzinfo=UTC), ctx) == 20.0  # 23:45 local, old
    assert price_cent(tariff, datetime(2026, 12, 31, 23, 0, tzinfo=UTC), ctx) == 25.0  # 00:00 local, new


def test_date_outside_every_version_is_an_error():
    tariff = versions({**BASE, "valid_from": "2026-01-01", "valid_to": "2026-06-30"}, {**BASE, "valid_from": "2026-08-01"})
    ctx = PricingContext("Europe/Vienna")
    assert code_of(price_cent, tariff, datetime(2026, 7, 15, 10, tzinfo=UTC), ctx) == ErrorCode.TARIFF_NOT_VALID
    assert code_of(price_cent, tariff, datetime(2025, 12, 15, 10, tzinfo=UTC), ctx) == ErrorCode.TARIFF_NOT_VALID
    single = parse_tariff({**BASE, "valid_from": "2027-01-01"}, IMPORT)
    assert code_of(price_cent, single, datetime(2026, 12, 1, 10, tzinfo=UTC), ctx) == ErrorCode.TARIFF_NOT_VALID


def test_overlapping_or_open_versions_are_rejected():
    first = {**BASE, "valid_from": "2026-01-01", "valid_to": "2026-12-31"}
    assert code_of(versions, first, {**BASE, "valid_from": "2026-12-31"}) == ErrorCode.TARIFF_VALIDITY_OVERLAP
    assert code_of(versions, {**BASE, "valid_from": "2026-01-01"}, {**BASE, "valid_from": "2027-01-01"}) == (
        ErrorCode.TARIFF_VALIDITY_OVERLAP
    )


def test_duplicates_without_validity_or_in_the_user_file_stay_collisions(tmp_path):
    assert code_of(versions, BASE, {**BASE, "valid_from": "2027-01-01"}) == ErrorCode.ID_COLLISION
    user = {**BASE, "id": "user_x"}
    document = {"tariff_format": 1, "import_tariffs": [{**user, "valid_to": "2026-12-31"}, {**user, "valid_from": "2027-01-01"}]}
    path = tmp_path / "user_tariffs.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert code_of(load_tariffs, None, path) == ErrorCode.ID_COLLISION


def test_valid_to_before_valid_from_is_rejected():
    assert code_of(parse_tariff, {**BASE, "valid_from": "2027-01-02", "valid_to": "2027-01-01"}, IMPORT) == ErrorCode.VALUE_INVALID


def test_editor_catalog_shows_the_version_valid_today(tmp_path):
    path = tmp_path / "tariffs.json"
    entries = [{**BASE, "valid_from": "2026-01-01", "valid_to": "2026-12-31"}, {**BASE, "fix_cent_kwh": 25, "valid_from": "2027-01-01"}]
    path.write_text(json.dumps(tariffs_doc(entries)), encoding="utf-8")
    assert [entry.raw["fix_cent_kwh"] for entry in read_catalog(path, today=TODAY)] == [20]
    assert [entry.raw["fix_cent_kwh"] for entry in read_catalog(path, today=date(2027, 3, 1))] == [25]
    assert [entry.raw["fix_cent_kwh"] for entry in read_catalog(path, today=date(2025, 3, 1))] == [25]  # none: newest


# --- P3: db_ref -----------------------------------------------------------------------------


def test_copy_carries_db_ref_and_drops_validity():
    ref = db_ref_for(BASE, IMPORT)
    copy = copy_as_template({**BASE, "valid_from": "2026-01-01", "check": CHECK}, set(), "(copy)", ref)
    assert copy["db_ref"] == {"id": "AT/import/at_x_fix", "version": tariff_version(BASE, IMPORT)}
    assert "valid_from" not in copy
    assert "check" not in copy  # the check covers the database entry, not the user's copy
    assert parse_tariff(copy, IMPORT).db_ref.id == "AT/import/at_x_fix"
    assert differs_from_db(copy, IMPORT) is False
    assert differs_from_db({**copy, "fix_cent_kwh": 21}, IMPORT) is True
    assert differs_from_db(BASE, IMPORT) is None


def test_unchanged_copy_still_matches_after_the_editor_round_trip():
    for raw, direction in ((BASE, IMPORT), (MONTHLY, IMPORT), ({"id": "at_y", "type": "fixed", "supplier_id": "y", "land": "AT", "k_push_cent": 7, "vat_percent": 0}, EXPORT)):
        copy = copy_as_template(raw, set(), "(copy)", db_ref_for(raw, direction))
        saved = TariffDraft.from_raw(copy, direction).to_raw()
        assert differs_from_db(saved, direction) is False, raw["id"]


@pytest.mark.parametrize(
    "ref",
    [
        {"id": "a", "version": "abc"},
        {"id": "a"},
        {"id": "a", "version": "0" * 64, "extra": 1},
    ],
)
def test_invalid_db_ref_is_rejected(ref):
    assert code_of(parse_tariff, {**BASE, "db_ref": ref}, IMPORT) in (
        ErrorCode.VALUE_INVALID, ErrorCode.FIELD_MISSING, ErrorCode.TARIFF_UNKNOWN_FIELD,
    )  # fmt: skip


def test_db_ref_of_contract_v1_needs_the_migration():
    """v1 named the database; v2 has one. The old key is never ignored, the migration removes it."""
    ref = {"database": "free", "id": "AT/import/x", "version": "0" * 64}
    assert code_of(parse_tariff, {**BASE, "id": "user_x", "db_ref": ref}, IMPORT) == ErrorCode.DB_REF_LEGACY


@pytest.mark.parametrize(
    ("check", "code"),
    [
        ({"state": "unchecked", "checked_at": "2026-10-01", "source": "s"}, ErrorCode.VALUE_INVALID),
        ({"state": "rejected", "checked_at": "2026-10-01", "source": "s"}, ErrorCode.VALUE_INVALID),
        ({"state": "checked", "source": "s"}, ErrorCode.FIELD_MISSING),
        ({"state": "checked", "checked_at": "2026-10-01"}, ErrorCode.FIELD_MISSING),
        ({"state": "released_by_supplier", "checked_at": "2026-10-01"}, ErrorCode.FIELD_MISSING),
        ({"state": "checked", "checked_at": "2026-10-01", "source": "s", "by": "x"}, ErrorCode.TARIFF_UNKNOWN_FIELD),
    ],
)
def test_check_block_is_strict(check, code):
    assert code_of(parse_tariff, {**BASE, "check": check}, IMPORT) == code


def test_check_is_not_part_of_the_version_and_not_allowed_in_user_files():
    released = {"state": "released_by_supplier", "checked_at": "2026-10-25", "released_by": "X Energie"}
    assert tariff_version({**BASE, "check": CHECK}, IMPORT) == tariff_version({**BASE, "check": released}, IMPORT) == tariff_version(BASE, IMPORT)
    assert parse_tariff({**BASE, "check": released}, IMPORT).check.released_by == "X Energie"
    user = tariffs_doc([{**BASE, "id": "user_x", "check": CHECK}])
    assert code_of(parse_tariff_documents, None, user) == ErrorCode.CHECK_NOT_IN_USER_FILE


# --- P4: package check ----------------------------------------------------------------------


def test_valid_package_passes(signing):
    package = verify_package(make_package(signing), trusted_keys=signing[1], today=TODAY)
    assert package.manifest.valid_until == date(2026, 12, 31)
    assert package.tariffs["import_tariffs"][0]["id"] == "at_x_fix"
    assert package.warnings == ()


def test_expired_package_is_usable_with_a_warning(signing):
    package = verify_package(make_package(signing, valid_until="2026-10-01"), trusted_keys=signing[1], today=TODAY)
    assert [note.code for note in package.warnings] == [WarningCode.PACKAGE_EXPIRED]


def test_unknown_key_and_built_in_keys(signing):
    document = make_package(signing)
    assert code_of(verify_package, document, today=TODAY) == ErrorCode.PACKAGE_KEY_UNKNOWN  # no built-in key yet
    other = {KEY_ID: public_key_text(Ed25519PrivateKey.generate().public_key())}
    assert code_of(verify_package, document, trusted_keys=other, today=TODAY) == ErrorCode.PACKAGE_SIGNATURE_INVALID


def test_any_change_breaks_the_package(signing):
    document = make_package(signing)
    changed_manifest = json.loads(json.dumps(document))
    changed_manifest["manifest"]["valid_until"] = "2030-12-31"
    assert code_of(verify_package, changed_manifest, trusted_keys=signing[1], today=TODAY) == ErrorCode.PACKAGE_SIGNATURE_INVALID
    changed_content = json.loads(json.dumps(document))
    changed_content["content"]["tariffs.json"]["import_tariffs"][0]["fix_cent_kwh"] = 1
    assert code_of(verify_package, changed_content, trusted_keys=signing[1], today=TODAY) == ErrorCode.PACKAGE_CONTENT_MISMATCH
    broken = {**document, "signature": "not base64!"}
    assert code_of(verify_package, broken, trusted_keys=signing[1], today=TODAY) == ErrorCode.PACKAGE_SIGNATURE_INVALID


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"edibert_package": 1}, ErrorCode.PACKAGE_FORMAT_UNSUPPORTED),  # format 1 (two databases) was never published
        ({"edibert_package": 3}, ErrorCode.PACKAGE_FORMAT_UNSUPPORTED),
        ({"edibert_package": True}, ErrorCode.PACKAGE_FORMAT_UNSUPPORTED),
        ({"extra": 1}, ErrorCode.TARIFF_UNKNOWN_FIELD),
    ],
)
def test_package_root_is_strict(signing, change, code):
    assert code_of(verify_package, {**make_package(signing), **change}, trusted_keys=signing[1]) == code


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"database": "verified"}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({"issued_at": "2026-10-29T08:00:00"}, ErrorCode.VALUE_INVALID),
        ({"valid_until": None}, ErrorCode.FIELD_MISSING),
        ({"tariff_format": "1"}, ErrorCode.VALUE_INVALID),
        ({"tariff_format": 2}, ErrorCode.VALUE_INVALID),
        ({"colour": "red"}, ErrorCode.TARIFF_UNKNOWN_FIELD),
    ],
)
def test_manifest_is_strict(signing, changes, code):
    assert code_of(verify_package, make_package(signing, **changes), trusted_keys=signing[1], today=TODAY) == code


def test_package_carries_checked_tariffs_only(signing):
    document = make_package(signing, unchecked=True)
    assert code_of(verify_package, document, trusted_keys=signing[1], today=TODAY) == ErrorCode.PACKAGE_ENTRY_UNCHECKED
    unchecked = tariffs_doc([{**BASE, "check": {**CHECK, "state": "unchecked"}}])
    document = make_package(signing, tariffs=unchecked, unchecked=True)
    assert code_of(verify_package, document, trusted_keys=signing[1], today=TODAY) == ErrorCode.VALUE_INVALID


def test_package_content_must_load_and_carry_identities(signing):
    bad_tariff = tariffs_doc([{**BASE, "fix_cent_kwh": "x"}])
    assert code_of(verify_package, make_package(signing, tariffs=bad_tariff), trusted_keys=signing[1]) == ErrorCode.VALUE_INVALID
    no_land = tariffs_doc([{key: value for key, value in BASE.items() if key != "land"}])
    assert code_of(verify_package, make_package(signing, tariffs=no_land), trusted_keys=signing[1]) == ErrorCode.FIELD_MISSING


# --- P5: import -----------------------------------------------------------------------------


def package_with(signing, tariffs, grid=None):
    return verify_package(make_package(signing, tariffs=tariffs, grid=grid), trusted_keys=signing[1], today=TODAY)


def test_plan_lists_changes_and_no_conflicts_for_a_first_import(signing):
    plan = plan_package_import(package_with(signing, tariffs_doc([BASE, MONTHLY])), None, None)
    assert {(item.key, item.change) for item in plan.changes} == {
        ("import/at_x_fix", "added"), ("import/at_x_monthly", "added"), ("grid/AT-X", "added"),
    }  # fmt: skip
    assert plan.conflicts == ()


def test_plan_finds_changed_removed_and_lost_monthly_rows(signing):
    local_monthly = {**MONTHLY, "monthly_rates": [*MONTHLY["monthly_rates"], {"year": 2026, "month": 11, "tariff_cent_kwh": 9.9}]}
    local = tariffs_doc([{**BASE, "fix_cent_kwh": 19}, local_monthly, {**BASE, "id": "at_gone"}])
    local["oemag_monthly_feed_in_rates"] = [{"year": 2026, "month": 10, "tariff_cent_kwh": 5.0}]
    package = package_with(signing, tariffs_doc([BASE, {**MONTHLY, "monthly_rates": [{"year": 2026, "month": 9, "tariff_cent_kwh": 9.0}, {"year": 2026, "month": 10, "tariff_cent_kwh": 9.6}]}]))
    plan = plan_package_import(package, local, grid_doc())
    assert {(item.key, item.change) for item in plan.changes} == {
        ("import/at_x_fix", "changed"), ("import/at_x_monthly", "changed"), ("import/at_gone", "removed"),
    }  # fmt: skip
    assert [(c.key, c.local_cent, c.package_cent) for c in plan.conflicts] == [
        ("import/at_x_monthly/2026-10", 9.5, 9.6),
        ("import/at_x_monthly/2026-11", 9.9, None),
        ("root/oemag_monthly_feed_in_rates/2026-10", 5.0, None),
    ]


def test_apply_needs_a_decision_for_every_conflict(signing):
    local = tariffs_doc([{**MONTHLY, "monthly_rates": [{"year": 2026, "month": 11, "tariff_cent_kwh": 9.9}]}])
    plan = plan_package_import(package_with(signing, tariffs_doc([MONTHLY])), local, None)
    assert code_of(apply_package_import, plan, {}) == ErrorCode.PACKAGE_IMPORT_CONFLICT
    assert code_of(apply_package_import, plan, {"import/at_x_monthly/2026-11": "maybe"}) == ErrorCode.VALUE_INVALID
    assert code_of(apply_package_import, plan, {"import/other/2026-11": KEEP_LOCAL}) == ErrorCode.VALUE_INVALID


def test_apply_keeps_or_drops_local_rows_and_stamps_the_package(signing):
    local = tariffs_doc([{**MONTHLY, "monthly_rates": [{"year": 2026, "month": 11, "tariff_cent_kwh": 9.9}]}])
    local["oemag_monthly_feed_in_rates"] = [{"year": 2026, "month": 10, "tariff_cent_kwh": 5.0}]
    plan = plan_package_import(package_with(signing, tariffs_doc([MONTHLY])), local, None)
    tariffs, grid = apply_package_import(
        plan, {"import/at_x_monthly/2026-11": KEEP_LOCAL, "root/oemag_monthly_feed_in_rates/2026-10": TAKE_PACKAGE}
    )
    rows = tariffs["import_tariffs"][0]["monthly_rates"]
    assert [(row["month"], row["tariff_cent_kwh"]) for row in rows] == [(9, 9.0), (10, 9.5), (11, 9.9)]
    assert "oemag_monthly_feed_in_rates" not in tariffs
    assert tariffs["package"] == {
        "package_id": "2026-10-a", "issued_at": "2026-10-29T08:00:00+00:00", "valid_until": "2026-12-31",
    }  # fmt: skip
    assert grid == grid_doc()
    assert plan.package.tariffs.get("package") is None  # the package itself is unchanged


def test_kept_row_goes_into_the_version_of_its_month(signing):
    old = {**MONTHLY, "valid_from": "2026-01-01", "valid_to": "2026-10-31"}
    new = {**MONTHLY, "valid_from": "2026-11-01", "monthly_rates": [{"year": 2026, "month": 11, "tariff_cent_kwh": 8.0}]}
    local = tariffs_doc([{**MONTHLY, "monthly_rates": [{"year": 2026, "month": 12, "tariff_cent_kwh": 8.5}]}])
    plan = plan_package_import(package_with(signing, tariffs_doc([old, new])), local, None)
    tariffs, _ = apply_package_import(plan, {"import/at_x_monthly/2026-12": KEEP_LOCAL})
    assert [len(entry["monthly_rates"]) for entry in tariffs["import_tariffs"]] == [2, 2]


def test_written_catalog_loads_and_names_its_package(signing, tmp_path):
    plan = plan_package_import(package_with(signing, tariffs_doc([BASE])), None, None)
    tariffs, grid = apply_package_import(plan, {})
    tariffs_path, grid_path = tmp_path / "cat" / "tariffs.json", tmp_path / "cat" / "grid_fees.json"
    write_catalog_pair(tariffs_path, tariffs, grid_path, grid)
    assert load_tariffs(tariffs_path).imports["at_x_fix"].fix_cent_kwh == 20.0
    assert catalog_package(tariffs_path)["package_id"] == "2026-10-a"
    assert load_tariffs(tariffs_path).imports["at_x_fix"].check.state == "checked"
    stale = json.loads(tariffs_path.read_text(encoding="utf-8"))
    stale["package"]["database"] = "verified"  # a catalog imported from a v1 package
    tariffs_path.write_text(json.dumps(stale), encoding="utf-8")
    assert code_of(catalog_package, tariffs_path) == ErrorCode.TARIFF_UNKNOWN_FIELD
    assert sorted(path.name for path in tariffs_path.parent.iterdir()) == ["grid_fees.json", "tariffs.json"]


# --- CLI ------------------------------------------------------------------------------------


def write_package(tmp_path, signing, tariffs):
    package_path, keys_path = tmp_path / "package.json", tmp_path / "keys.json"
    package_path.write_text(json.dumps(make_package(signing, tariffs=tariffs, valid_until="2099-12-31")), encoding="utf-8")
    keys_path.write_text(json.dumps(signing[1]), encoding="utf-8")
    return package_path, keys_path


def test_cli_verify_and_import(tmp_path, signing, capsys):
    package_path, keys_path = write_package(tmp_path, signing, tariffs_doc([MONTHLY]))
    assert main(["package", "verify", str(package_path), "--trusted-keys", str(keys_path)]) == 0
    assert "2026-10-a" in capsys.readouterr().out
    assert main(["package", "verify", str(package_path)]) == 2  # built-in keys do not know the test key
    catalog, grid = tmp_path / "tariffs.json", tmp_path / "grid_fees.json"
    catalog.write_text(json.dumps(tariffs_doc([{**MONTHLY, "monthly_rates": [{"year": 2026, "month": 11, "tariff_cent_kwh": 9.9}]}])), encoding="utf-8")
    common = ["package", "import", str(package_path), "--trusted-keys", str(keys_path), "--catalog", str(catalog), "--grid-catalog", str(grid)]
    assert main([*common, "--dry-run"]) == 0
    assert "import/at_x_monthly/2026-11" in capsys.readouterr().out
    assert not grid.exists()
    assert main(common) == 2  # undecided conflict
    assert "package" not in json.loads(catalog.read_text(encoding="utf-8"))
    assert main([*common, "--keep-local", "import/at_x_monthly/2026-11"]) == 0
    written = json.loads(catalog.read_text(encoding="utf-8"))
    assert written["package"]["package_id"] == "2026-10-a"
    assert len(written["import_tariffs"][0]["monthly_rates"]) == 3
    assert grid.exists()
