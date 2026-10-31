"""Grid areas, 0.1.d2: components, fixed yearly amounts, levy sets, regions, version, package, migration, sharing."""

import copy
import json
from datetime import date

import pytest
from conftest import at

from edibert.cli import main
from edibert.contribution import (
    grid_contribution_item,
    grid_contribution_payload,
    grid_payload_entry,
)
from edibert.editor.house import HOUSE_GRID_AREA, GridDraft, HouseSettings
from edibert.editor.invoice import invoice_check
from edibert.errors import EdibertError, ErrorCode
from edibert.exchange import (
    DB_ID,
    ExchangeClient,
    ExchangeConfig,
    HttpAnswer,
    payload_version,
    used_grid_ref,
)
from edibert.gridfee import (
    CATALOG,
    USER,
    area_document,
    parse_grid_fee_catalog,
    parse_grid_fee_config,
    resolve_grid_fee,
    user_area_entry,
)
from edibert.identity import (
    entry_version,
    grid_area_version,
    grid_db_ref_for,
    grid_differs_from_db,
)
from edibert.migration import migrate, plan_migration
from edibert.series import tariff_price_series
from edibert.tariff import IMPORT, evaluate, parse_tariff

SNAP = {
    "id": "SNAP", "label": "Summer low", "status": "verordnet", "months": [4, 5, 6, 7, 8, 9],
    "time": {"from": "10:00", "to": "16:00"}, "effect": {"mode": "percent_off", "value": 20.0},
    "requires": ["quarter_hour_meter"], "valid_to": None, "weekdays": None, "source": "x", "note": "y",
}  # fmt: skip
LEVIES = {
    "label": "Levies NE7 (placeholder)",
    "components": [
        {"id": "renewables_work", "label": "Renewables on work", "cent_kwh": {"unmetered_power": 0.5, "metered_power": 0.3}},
        {"id": "renewables_loss", "label": "Renewables on loss", "cent_kwh": 0.03},
    ],
    "fixed_eur_year": [{"id": "renewables_flat", "label": "Renewables flat fee", "eur_year": 20.0}],
}
AREA = {
    "id": "AT-Q", "label": "Q-Land", "land": "AT", "regions": ["8"], "operator": "Q Netz",
    "base_cent_kwh": {"unmetered_power": 5.0, "metered_power": 3.0}, "rule_set": "AT_NE7",
    "components": [{"id": "grid_loss", "label": "Grid loss", "cent_kwh": 0.4}],
    "fixed_eur_year": [{"id": "base_fee", "label": "Base fee", "eur_year": {"unmetered_power": 50.0, "metered_power": None}}],
    "levy_set": "AT_NE7_LEVIES", "source": "placeholder sheet",
}  # fmt: skip
DOC = {"tariff_format": 1, "rule_sets": {"AT_NE7": [SNAP]}, "levy_sets": {"AT_NE7_LEVIES": LEVIES}, "areas": [AREA]}
NET = {"id": "user_net", "type": "fixed_cent", "supplier_id": "user_x", "land": "AT", "fix_cent_kwh": 10.0,
       "prices_include_vat": False, "vat_percent": 20}  # fmt: skip


def fee(document=DOC, area_id="AT-Q", origin=CATALOG, **config):
    grids = parse_grid_fee_catalog(document, origin)
    return resolve_grid_fee(parse_grid_fee_config({"area_id": area_id, "quarter_hour_meter": True, **config}), grids)


def code_of(func, *args, **kwargs):
    with pytest.raises(EdibertError) as err:
        func(*args, **kwargs)
    return err.value.code


# --- format and engine -------------------------------------------------------------------------------------------


def test_components_and_levies_are_added_to_the_work_price_rules_change_the_work_price_only(ctx_at):
    grid = fee()
    july_noon = grid.slot(ctx_at.to_local(at("2026-07-15 12:00")), ctx_at)
    assert july_noon.rule_id == "SNAP" and july_noon.work_cent == pytest.approx(4.0)  # 20 % off the work price only
    assert dict(july_noon.components) == {"grid_loss": 0.4, "renewables_work": 0.5, "renewables_loss": 0.03}
    assert july_noon.total_cent == pytest.approx(4.93)
    assert [part.id for part in grid.fixed] == ["base_fee", "renewables_flat"] and grid.fixed_eur_year == 70.0


def test_evaluate_carries_the_breakdown_and_vat_covers_the_whole_grid_fee(ctx_at):
    result = evaluate(parse_tariff(NET, IMPORT), at("2026-11-02 12:00"), ctx_at, None, fee())
    assert result.grid_cent == pytest.approx(5.93)
    assert result.grid_breakdown[0] == ("work", 5.0) and len(result.grid_breakdown) == 4
    assert result.cent == pytest.approx(round((10.0 + 5.93) * 1.2, 4))


def test_metered_power_without_a_modeled_base_fee_is_an_error_never_zero():
    assert code_of(fee, power_metering="metered_power") == ErrorCode.GRID_METERING_NOT_MODELED


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"levy_set": "NOPE"}, ErrorCode.VALUE_INVALID),
        ({"regions": ["99"]}, ErrorCode.VALUE_INVALID),
        ({"components": [{"id": "work", "cent_kwh": 1}]}, ErrorCode.VALUE_INVALID),  # reserved breakdown key
        ({"components": [{"id": "renewables_work", "cent_kwh": 1}]}, ErrorCode.VALUE_INVALID),  # clashes with the levy set
        ({"components": [{"id": "x"}]}, ErrorCode.FIELD_MISSING),
        ({"components": [{"id": "x", "cent_kwh": {"unmetered_power": 1}}]}, ErrorCode.FIELD_MISSING),
        ({"fixed_eur_year": [{"id": "x", "eur_year": -1}]}, ErrorCode.VALUE_INVALID),
        ({"fixed_eur_year": [{"id": "x", "eur_year": 1, "per": "year"}]}, ErrorCode.TARIFF_UNKNOWN_FIELD),
        ({"db_ref": {"id": "AT/grid/x", "version": "a" * 64}}, ErrorCode.VALUE_INVALID),  # catalog areas have none
    ],
)
def test_area_load_checks(change, code):
    document = copy.deepcopy(DOC)
    document["areas"][0].update(change)
    assert code_of(parse_grid_fee_catalog, document, CATALOG) == code


def test_user_file_rejects_a_database_check_and_levy_sets_follow_the_prefix_rule():
    entry = area_document(DOC, "AT-Q")
    area, rule_sets, levy_sets = user_area_entry(entry, "user_home")
    user = {"tariff_format": 1, "rule_sets": rule_sets, "levy_sets": levy_sets, "areas": [area]}
    parse_grid_fee_catalog(user, USER)
    checked = {**area, "check": {"state": "checked", "checked_at": "2026-10-31", "source": "sheet"}}
    assert code_of(parse_grid_fee_catalog, {**user, "areas": [checked]}, USER) == ErrorCode.CHECK_NOT_IN_USER_FILE
    assert code_of(parse_grid_fee_catalog, {**user, "levy_sets": {"bad": LEVIES}}, USER) == ErrorCode.GRID_ID_PREFIX_MISSING


def test_regions_narrow_the_catalog_choice():
    grids = parse_grid_fee_catalog(DOC, CATALOG)
    assert [area.id for area in grids.areas_for("AT", "8")] == ["AT-Q"]
    assert grids.areas_for("AT", "7") == [] and grids.areas_for("DE", "8") == []
    whole = copy.deepcopy(DOC)
    del whole["areas"][0]["regions"]
    assert [area.id for area in parse_grid_fee_catalog(whole, CATALOG).areas_for("AT", "7")] == ["AT-Q"]


def test_series_has_a_breakdown_per_point_and_the_fixed_block_apart(ctx_at):
    tariff = parse_tariff(NET, IMPORT)
    series = tariff_price_series(tariff, ctx_at, at("2026-11-02 00:00"), at("2026-11-02 01:00"), resolution_min=60, grid_fee=fee())
    data = series.to_dict()
    assert data["points"][0]["grid_breakdown"]["grid_loss"] == 0.4
    assert data["grid_fixed"] == {
        "area_id": "AT-Q", "unit": "EUR per year, net", "total_eur_year": 70.0,
        "items": [{"id": "base_fee", "label": "Base fee", "eur_year": 50.0},
                  {"id": "renewables_flat", "label": "Renewables flat fee", "eur_year": 20.0}],
    }  # fmt: skip
    assert data["points"][0]["grid_cent"] == pytest.approx(5.93)  # the fixed amounts are never in a slot price
    plain = tariff_price_series(tariff, ctx_at, at("2026-11-02 00:00"), at("2026-11-02 01:00"), resolution_min=60).to_dict()
    assert "grid_fixed" not in plain and "grid_breakdown" not in plain["points"][0]


def test_invoice_check_adds_one_twelfth_of_the_fixed_amounts_with_vat(ctx_at):
    tariff = parse_tariff(NET, IMPORT)
    check = invoice_check(tariff, ctx_at, date(2026, 11, 1), {"base": 100.0}, 30.0, grid_fee=fee())
    assert check.grid_fixed_eur == pytest.approx(70.0 / 12 * 1.2, abs=0.01)
    assert check.expected_eur == pytest.approx(check.energy_eur + check.fees_eur + check.grid_fixed_eur, abs=0.01)


# --- identity and version ----------------------------------------------------------------------------------------


def test_version_covers_components_fixed_amounts_and_levies_not_names():
    version = grid_area_version(AREA, DOC["rule_sets"], DOC["levy_sets"])
    renamed = {**AREA, "label": "Other", "operator": "Other", "regions": ["7"], "source": "z"}
    assert grid_area_version(renamed, DOC["rule_sets"], DOC["levy_sets"]) == version
    other_set = {**AREA, "rule_set": "R", "levy_set": "L"}
    assert grid_area_version(other_set, {"R": [{**SNAP, "id": "x", "label": "z"}]}, {"L": LEVIES}) == version
    for changed in (
        {**AREA, "components": [{"id": "grid_loss", "cent_kwh": 0.5}]},
        {**AREA, "fixed_eur_year": [{"id": "base_fee", "eur_year": 51.0}]},
    ):
        assert grid_area_version(changed, DOC["rule_sets"], DOC["levy_sets"]) != version
    levies = copy.deepcopy(LEVIES)
    levies["fixed_eur_year"][0]["eur_year"] = 21.0
    assert grid_area_version(AREA, DOC["rule_sets"], {"AT_NE7_LEVIES": levies}) != version
    assert code_of(grid_area_version, AREA, DOC["rule_sets"]) == ErrorCode.VALUE_INVALID  # levy set not given


def test_copy_as_own_values_keeps_the_version_and_tells_when_it_differs():
    ref = grid_db_ref_for(DOC, "AT-Q")
    assert ref["id"] == "AT/grid/AT-Q"
    draft = GridDraft.from_entry(area_document(DOC, "AT-Q"))
    draft.extra["db_ref"] = ref
    document = draft.document()
    assert grid_differs_from_db(document, HOUSE_GRID_AREA) is False  # saved through the editor unchanged
    draft.base["unmetered_power"] = 5.1
    assert grid_differs_from_db(draft.document(), HOUSE_GRID_AREA) is True
    assert DB_ID.match("AT/grid/AT-VBG") and DB_ID.match("AT/grid/shared_abc") and not DB_ID.match("AT/import/AT-X")


# --- package --------------------------------------------------------------------------------------------------------


def test_package_needs_a_check_on_every_grid_area():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from edibert.package import build_package, public_key_text, verify_package

    key = Ed25519PrivateKey.generate()
    keys = {"k": public_key_text(key.public_key())}
    manifest = {"package_id": "p", "issued_at": "2026-10-31T08:00:00+00:00", "valid_until": "2026-12-31", "tariff_format": 1, "key_id": "k"}
    tariffs = {"tariff_format": 1, "import_tariffs": [], "export_tariffs": []}
    package = build_package(tariffs, DOC, manifest, key)
    assert code_of(verify_package, package, trusted_keys=keys, today=date(2026, 11, 1)) == ErrorCode.PACKAGE_ENTRY_UNCHECKED
    checked = copy.deepcopy(DOC)
    checked["areas"][0]["check"] = {"state": "checked", "checked_at": "2026-10-31", "source": "price sheet"}
    verified = verify_package(build_package(tariffs, checked, manifest, key), trusted_keys=keys, today=date(2026, 11, 1))
    assert verified.grid_fees["areas"][0]["check"]["state"] == "checked"


def test_operator_file_check_on_the_command_line(tmp_path, capsys):
    path = tmp_path / "grid.json"
    path.write_text(json.dumps(DOC), encoding="utf-8")
    assert main(["grid", "check", str(path)]) == 0
    out = capsys.readouterr().out
    assert "AT/grid/AT-Q" in out and "70" in out and "–" in out  # metered power: base fee not modeled
    assert main(["grid", "check", str(path), "--require-check"]) == 2
    broken = copy.deepcopy(DOC)
    broken["areas"][0]["levy_set"] = "NOPE"
    path.write_text(json.dumps(broken), encoding="utf-8")
    assert main(["grid", "check", str(path)]) == 2


# --- migration of grid_monthly_fee_eur ----------------------------------------------------------------------------


def user_doc(*tariffs):
    return {"tariff_format": 1, "import_tariffs": list(tariffs), "export_tariffs": []}


GROSS = {"id": "user_a", "type": "fixed_cent", "supplier_id": "user_x", "land": "AT", "fix_cent_kwh": 20, "vat_percent": 20,
         "grid_monthly_fee_eur": 6.0}  # fmt: skip
OWN = {"id": "user_house", "base_cent_kwh": {"unmetered_power": 5.0, "metered_power": 5.0}}


def test_a_tariff_with_the_old_field_fails_loudly():
    assert code_of(parse_tariff, GROSS, IMPORT) == ErrorCode.GRID_MONTHLY_FEE_LEGACY


def test_migration_moves_one_value_net_into_the_own_area():
    docs = {"user_tariffs.json": user_doc(GROSS), "user_grid_fees.json": {"tariff_format": 1, "areas": [OWN]}}
    plan = plan_migration(docs, grid_fee_area="user_house")
    assert plan.can_run and set(plan.changed_files) == {"user_tariffs.json", "user_grid_fees.json"}
    result = migrate(docs, grid_fee_area="user_house")
    assert "grid_monthly_fee_eur" not in result.docs["user_tariffs.json"]["import_tariffs"][0]
    (fixed,) = result.docs["user_grid_fees.json"]["areas"][0]["fixed_eur_year"]
    assert fixed["id"] == "grid_base_fee" and fixed["eur_year"] == 60.0  # 6 EUR gross a month = 72 / 1.2 net a year
    again = migrate(result.docs, grid_fee_area="user_house")
    assert again.changed_files == ()


def test_migration_never_guesses_the_target_or_the_value():
    two = {**GROSS, "id": "user_b", "grid_monthly_fee_eur": 7.0}
    docs = {"user_tariffs.json": user_doc(GROSS, two), "user_grid_fees.json": {"tariff_format": 1, "areas": [OWN]}}
    assert [b.code for b in plan_migration(docs, grid_fee_area="user_house").blockers] == [ErrorCode.GRID_MONTHLY_FEE_AMBIGUOUS]
    single = {"user_tariffs.json": user_doc(GROSS)}
    for area in (None, "AT-VBG", "user_missing"):  # no own area, a catalog area, an area that does not exist
        blockers = migrate(single, grid_fee_area=area).blockers
        assert [b.code for b in blockers] == [ErrorCode.GRID_MONTHLY_FEE_NO_TARGET]
    zero = {"user_tariffs.json": user_doc({**GROSS, "grid_monthly_fee_eur": 0})}
    result = migrate(zero)  # 0 moves nothing and needs no target
    assert not result.blockers and "grid_monthly_fee_eur" not in result.docs["user_tariffs.json"]["import_tariffs"][0]


def test_migration_waits_for_the_vat_answer_before_it_moves_the_fee():
    no_vat = {k: v for k, v in GROSS.items() if k != "vat_percent"}
    docs = {"user_tariffs.json": user_doc(no_vat), "user_grid_fees.json": {"tariff_format": 1, "areas": [OWN]}}
    plan = plan_migration(docs, grid_fee_area="user_house")
    assert plan.can_run and [q.id for q in plan.questions] == ["vat_percent:import:user_a"]
    assert "user_grid_fees.json" in plan.changed_files
    result = migrate(docs, {"vat_percent:import:user_a": 0}, grid_fee_area="user_house")
    assert result.docs["user_grid_fees.json"]["areas"][0]["fixed_eur_year"][0]["eur_year"] == 72.0


def test_editor_house_migration_moves_the_own_grid_fee_and_the_monthly_fee():
    house = HouseSettings.from_json({"land": "AT", "grid_enabled": True, "grid_base_cent": 5.0,
                                     "grid_rules": [{"id": "n", "time": {"from": "00:00", "to": "06:00"}, "effect": {"mode": "add_cent", "value": -1}}]})  # fmt: skip
    areas, rule_sets, own = house.legacy_migration_input()
    result = migrate({"user_tariffs.json": user_doc(GROSS)}, user_grid_areas=areas, user_grid_rule_sets=rule_sets, grid_fee_area=own)
    assert not result.blockers
    grids = parse_grid_fee_catalog(result.docs["user_grid_fees.json"], USER)
    migrated = house.migrated()
    grid = migrated.grid_fee(grids)
    assert grid is not None and grid.fixed_eur_year == 60.0 and len(grid.rules) == 1


# --- sharing and exchange ------------------------------------------------------------------------------------------


def own_document():
    area, rule_sets, levy_sets = user_area_entry(area_document(DOC, "AT-Q"), "user_house")
    area["db_ref"] = grid_db_ref_for(DOC, "AT-Q")
    return {"tariff_format": 1, "rule_sets": rule_sets, "levy_sets": levy_sets, "areas": [area]}


def test_grid_payload_is_a_whitelist_and_keeps_the_version():
    document = own_document()
    payload = grid_contribution_payload(document, "user_house")
    body = payload["grid_area"]
    assert payload["direction"] == "grid" and "id" not in body and "db_ref" not in body
    assert body["components"] == [{"id": "grid_loss", "cent_kwh": 0.4}]  # free-text labels dropped
    assert all("label" not in rule and "source" not in rule for rule in body["rules"])
    assert payload_version(payload) == entry_version(area_document(document, "user_house")) == document["areas"][0]["db_ref"]["version"]
    item = grid_contribution_item(document, "user_house", "Own")
    assert item.shareable and item.db_ref is not None and item.db_ref.id == "AT/grid/AT-Q"
    assert grid_contribution_item(None, "user_house", "Own").error.code == ErrorCode.CONTRIBUTION_GRID_AREA_UNAVAILABLE
    landless = copy.deepcopy(document)
    del landless["areas"][0]["land"]
    del landless["areas"][0]["regions"]
    assert code_of(grid_contribution_payload, landless, "user_house") == ErrorCode.CONTRIBUTION_LAND_MISSING


def test_grid_submit_route_and_grid_templates():
    payload = grid_contribution_payload(own_document(), "user_house")
    version = payload_version(payload)
    seen = []

    def send(method, url, body, headers, timeout):
        seen.append((method, url, None if body is None else json.loads(body)))
        if method == "POST":
            return HttpAnswer(200, {}, json.dumps({"status": "accepted", "code": None, "db_id": "AT/grid/shared_q", "version": version}).encode())
        item = {"db_id": "AT/grid/shared_q", "version": version, "direction": "grid", "grid_area": payload["grid_area"],
                "valid_from": None, "check_state": "unchecked", "reliable": False, "installations_12m": 1,
                "latest_version": version, "latest_checked_version": None}  # fmt: skip
        return HttpAnswer(200, {}, json.dumps({"templates": [item], "truncated": False}).encode())

    client = ExchangeClient(ExchangeConfig("https://db.test"), send, env={})
    answer = client.submit(payload)
    assert seen[0][1].endswith("/edibert/v1/grid_areas") and seen[0][2]["version"] == version
    assert answer.db_ref.id == "AT/grid/shared_q"
    (template,) = client.list_templates("AT", "grid").templates
    assert template.tariff == {} and entry_version(template.entry()) == version
    draft = GridDraft.from_entry(template.entry())
    assert draft.base == {"unmetered_power": 5.0, "metered_power": 3.0}
    bad = copy.deepcopy(payload["grid_area"])
    bad["base_cent_kwh"]["unmetered_power"] = 9.0
    assert payload_version({"direction": "grid", "grid_area": bad}) != version
    assert grid_payload_entry(payload["grid_area"])["levies"]["fixed_eur_year"][0]["eur_year"] == 20.0


def test_used_grid_ref_counts_unchanged_copies_and_package_areas():
    document = own_document()
    assert used_grid_ref(document, "user_house", False).id == "AT/grid/AT-Q"
    changed = copy.deepcopy(document)
    changed["areas"][0]["base_cent_kwh"]["unmetered_power"] = 9.0
    assert used_grid_ref(changed, "user_house", False) is None
    assert used_grid_ref(DOC, "AT-Q", True).id == "AT/grid/AT-Q"
    assert used_grid_ref(DOC, "AT-Q", False) is None and used_grid_ref(DOC, None, True) is None


def test_components_example_loads_and_prices(ctx_at):
    from conftest import load_example

    document = load_example("grid_fee_components_example.json")
    grid = fee(document, "user_home", USER)
    assert grid.fixed_eur_year == 70.0 and [part.id for part in grid.components] == ["grid_loss", "renewables_work", "renewables_loss"]
