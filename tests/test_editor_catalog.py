"""Copy-from-catalog helpers (``edibert.editor.catalog``) and the optional ``regions`` tariff field."""

import json

import pytest

from edibert.editor.catalog import (
    CatalogEntry,
    filter_entries,
    lands_of,
    read_catalog,
    settlement_interval,
    type_key,
    type_keys_of,
)
from edibert.editor.model import TariffDraft
from edibert.errors import EdibertError, ErrorCode
from edibert.tariff import EXPORT, IMPORT, parse_tariff


def tariff(tariff_id: str, label: str, tariff_type: str = "fixed_cent", land: str = "AT", **extra) -> dict:
    return {"id": tariff_id, "label": label, "type": tariff_type, "land": land, "supplier_id": "demo", "vat_percent": 20, **extra}


ENTRIES = [
    CatalogEntry(EXPORT, tariff("at_feed", "Alpha feed-in", "spot_hourly", settlement_mtu="15min")),
    CatalogEntry(IMPORT, tariff("at_zeta", "zeta fixed", fix_cent_kwh=12.0)),
    CatalogEntry(IMPORT, tariff("at_spot_h", "Beta spot", "spot_hourly", settlement_mtu="60min")),
    CatalogEntry(IMPORT, tariff("at_vlbg", "Vorarlberg fixed", regions=["8"], fix_cent_kwh=10.0)),
    CatalogEntry(IMPORT, tariff("de_fix", "Delta", land="DE", regions=["BY"], fix_cent_kwh=30.0)),
    CatalogEntry(IMPORT, tariff("at_table", "Monthly", "monthly_table", monthly_rates=[{"year": 2026, "month": 1, "tariff_cent_kwh": 9.0}])),
]


def ids(entries: list[CatalogEntry]) -> list[str]:
    return [entry.raw["id"] for entry in entries]


def test_type_keys_use_the_price_kinds_and_split_market_prices_by_interval():
    assert [type_key(e.raw, e.direction) for e in ENTRIES] == ["spot:15min", "fixed", "spot:60min", "fixed", "fixed", "monthly"]
    assert type_keys_of(ENTRIES) == ["fixed", "spot:15min", "spot:60min", "monthly"]
    assert type_key(tariff("x", "x", "spot_hourly"), IMPORT) == "spot:15min"  # interval defaults to 15 minutes


def test_settlement_interval_only_for_market_prices():
    assert settlement_interval(ENTRIES[2].raw, IMPORT) == "60min"
    assert settlement_interval(ENTRIES[1].raw, IMPORT) is None
    with pytest.raises(EdibertError):
        settlement_interval(tariff("x", "x", "spot_hourly", settlement_mtu="30min"), IMPORT)


def test_without_direction_filter_imports_come_first_sorted_by_label():
    shown = filter_entries(ENTRIES, land="AT", direction=None, kind=None, house_land="AT", house_region="8")
    assert ids(shown) == ["at_spot_h", "at_table", "at_vlbg", "at_zeta", "at_feed"]


def test_regional_tariff_is_hidden_outside_its_region():
    shown = filter_entries(ENTRIES, land="AT", direction=IMPORT, kind="fixed", house_land="AT", house_region="9")
    assert ids(shown) == ["at_zeta"]


def test_without_a_house_region_regional_tariffs_stay_visible():
    shown = filter_entries(ENTRIES, land=None, direction=IMPORT, kind="fixed", house_land="AT", house_region=None)
    assert ids(shown) == ["de_fix", "at_vlbg", "at_zeta"]


def test_regions_of_another_land_are_not_checked_against_the_house():
    shown = filter_entries(ENTRIES, land="DE", direction=None, kind=None, house_land="AT", house_region="8")
    assert ids(shown) == ["de_fix"]


def test_read_catalog_and_lands(tmp_path):
    path = tmp_path / "tariffs.json"
    path.write_text(json.dumps({"tariff_format": 1, "import_tariffs": [ENTRIES[1].raw], "export_tariffs": [ENTRIES[0].raw]}), encoding="utf-8")
    entries = read_catalog(path)
    assert [(e.direction, e.raw["id"]) for e in entries] == [(IMPORT, "at_zeta"), (EXPORT, "at_feed")]
    assert lands_of(ENTRIES) == ["AT", "DE"]


def test_regions_are_parsed_and_kept_by_the_form_model():
    raw = tariff("at_vlbg", "Vorarlberg", regions=["8"], fix_cent_kwh=10.0)
    assert parse_tariff(raw, IMPORT).regions == ("8",)
    assert TariffDraft.from_raw(raw, IMPORT).to_raw()["regions"] == ["8"]
    assert "regions" not in TariffDraft.from_raw(tariff("at_x", "x", fix_cent_kwh=1.0), IMPORT).to_raw()


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"regions": ["Vorarlberg"]}, ErrorCode.VALUE_INVALID),
        ({"regions": []}, ErrorCode.VALUE_INVALID),
        ({"regions": ["8", "8"]}, ErrorCode.VALUE_INVALID),
        ({"regions": "8"}, ErrorCode.VALUE_INVALID),
        ({"regions": ["8"], "land": None}, ErrorCode.FIELD_MISSING),
    ],
)
def test_invalid_regions_are_rejected(changes, code):
    raw = {**tariff("at_vlbg", "Vorarlberg", fix_cent_kwh=10.0), **changes}
    raw = {key: value for key, value in raw.items() if value is not None}
    with pytest.raises(EdibertError) as err:
        parse_tariff(raw, IMPORT)
    assert err.value.code == code
