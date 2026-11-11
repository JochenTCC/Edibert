"""Tariff overview model (Editor P4a): rows, columns, filters, price basis and the monthly value."""

import json
from datetime import date

import pytest

from edibert.editor.catalog import read_catalog
from edibert.editor.overview import (
    Basis,
    Origin,
    OverviewFilter,
    build_rows,
    columns,
    counts,
    filter_rows,
    kinds_of,
    lands_of,
    month_value,
    on_basis,
    row_values,
)
from edibert.errors import EdibertError, ErrorCode
from edibert.tariff import EXPORT, IMPORT

TODAY = date(2026, 11, 11)


def entry(tariff_id: str, label: str, tariff_type: str = "fixed_cent", land: str = "AT", **extra) -> dict:
    """A catalog entry with placeholder prices (no real supplier data)."""
    return {"id": tariff_id, "label": label, "type": tariff_type, "land": land, "supplier_id": f"supplier_{tariff_id}", "vat_percent": 20, **extra}


CATALOG = {
    "tariff_format": 1,
    "import_tariffs": [
        entry("at_fix", "Fix Gross", fix_cent_kwh=24.0, monthly_fee_eur=3.0, metering_monthly_fee_eur=1.2),
        entry("at_spot", "Spot Net", "spot_hourly", settlement_mtu="60min", prices_include_vat=False,
              markup_percent=2.0, settlement_fee_cent_kwh=1.5, price_floor_cent_kwh=0.0, price_cap_cent_kwh=40.0,
              requires=["smart_meter"], rules=[{"id": "night", "time": {"from": "22:00", "to": "06:00"},
                                                  "effect": {"mode": "absolute_cent", "value": 10.0}}]),
        entry("at_month", "Monthly Now", "monthly_table", monthly_rates=[{"year": 2026, "month": 11, "tariff_cent_kwh": 12.0}]),
        entry("at_old_month", "Monthly Old", "monthly_table", monthly_rates=[{"year": 2026, "month": 10, "tariff_cent_kwh": 11.0}]),
        entry("at_wien", "Vienna Only", regions=["9"], fix_cent_kwh=20.0),
        entry("de_fix", "Germany Fix", land="DE", fix_cent_kwh=30.0),
        entry("at_versions", "Versioned", fix_cent_kwh=10.0, valid_from="2026-01-01", valid_to="2026-12-31"),
        entry("at_versions", "Versioned", fix_cent_kwh=15.0, valid_from="2027-01-01"),
    ],
    "export_tariffs": [
        entry("at_feed_fix", "Feed Fix", "fixed", k_push_cent=8.0, prices_include_vat=False, vat_percent=0),
        entry("at_feed_spot", "Feed Spot", "spot_hourly", prices_include_vat=False, feed_in_fee_factor=0.1,
              settlement_fee_cent_kwh=0.5, feed_in_fix_cent=0.25),
    ],
}  # fmt: skip

USER = {
    "tariff_format": 1,
    "import_tariffs": [
        {"id": "user_mine", "label": "My Fix", "type": "fixed_cent", "supplier_id": "user_me", "fix_cent_kwh": 25.0,
         "vat_percent": 20, "prices_include_vat": False},
    ],
    "export_tariffs": [],
}  # fmt: skip


@pytest.fixture
def catalog(tmp_path):
    path = tmp_path / "tariffs.json"
    path.write_text(json.dumps(CATALOG), encoding="utf-8")
    return read_catalog(path, TODAY)


def by_label(rows, label):
    (row,) = [row for row in rows if row.tariff.label == label]
    return row


def test_rows_own_first_then_catalog_with_origin(catalog):
    rows = build_rows(IMPORT, USER, catalog)
    assert [row.origin for row in rows[:2]] == [Origin.OWN, Origin.CATALOG]
    assert rows[0].key == "own:user_mine"
    assert [row.tariff.id for row in rows].count("at_versions") == 1  # one validity version only
    assert counts(rows) == {Origin.OWN: 1, Origin.CATALOG: 7, Origin.TEMPLATE: 0}
    assert [row.tariff.id for row in build_rows(EXPORT, USER, catalog)] == ["at_feed_fix", "at_feed_spot"]


def test_the_version_valid_today_is_shown(tmp_path):
    path = tmp_path / "tariffs.json"
    path.write_text(json.dumps(CATALOG), encoding="utf-8")
    now = by_label(build_rows(IMPORT, USER, read_catalog(path, TODAY)), "Versioned")
    later = by_label(build_rows(IMPORT, USER, read_catalog(path, date(2027, 2, 1))), "Versioned")
    assert row_values(now, Basis.GROSS, TODAY).values["base_price"] == 10.0
    assert row_values(later, Basis.GROSS, TODAY).values["valid_from"] == date(2027, 1, 1)
    assert row_values(later, Basis.GROSS, TODAY).values["base_price"] == 15.0


def test_columns_per_direction():
    imports = [column.id for column in columns(IMPORT)]
    exports = [column.id for column in columns(EXPORT)]
    assert {"base_price", "markup_percent", "markup_cent"} <= set(imports)
    assert not {"remuneration", "market_factor", "fixed_deduction"} & set(imports)
    assert {"remuneration", "market_factor", "fixed_deduction", "fixed_addition"} <= set(exports)
    common = ["label", "supplier", "origin", "kind", "monthly_fee", "land", "regions", "time_rules", "price_floor",
              "price_cap", "requires", "valid_from", "valid_to", "last_verified", "check"]  # fmt: skip
    assert set(common) <= set(imports) and set(common) <= set(exports)
    assert 7 <= sum(column.default for column in columns(IMPORT)) <= 9
    with pytest.raises(ValueError, match="direction"):
        columns("both")


def test_import_values_of_fixed_and_spot(catalog):
    rows = build_rows(IMPORT, USER, catalog)
    fixed = row_values(by_label(rows, "Fix Gross"), Basis.GROSS, TODAY).values
    assert fixed["kind"] == "fixed" and fixed["base_price"] == 24.0
    assert fixed["markup_percent"] is None and fixed["markup_cent"] is None  # no effect on a fixed price
    assert fixed["monthly_fee"] == pytest.approx(4.2)
    assert fixed["supplier"] == "supplier_at_fix" and fixed["origin"] == "catalog"
    spot = row_values(by_label(rows, "Spot Net"), Basis.NET, TODAY).values
    assert spot["kind"] == "spot:60min" and spot["base_price"] is None
    assert spot["markup_percent"] == 2.0 and spot["markup_cent"] == 1.5
    assert spot["price_floor"] == 0.0 and spot["price_cap"] == 40.0
    assert spot["time_rules"] == 1 and spot["requires"] == ["smart_meter"]
    assert spot["monthly_fee"] is None
    assert by_label(rows, "Vienna Only").tariff.regions == ("9",)
    assert row_values(by_label(rows, "Vienna Only"), Basis.GROSS, TODAY).values["regions"] == "9"


def test_export_values(catalog):
    rows = build_rows(EXPORT, USER, catalog)
    fixed = row_values(by_label(rows, "Feed Fix"), Basis.GROSS, TODAY).values
    assert fixed["remuneration"] == 8.0  # 0 % VAT: gross equals net
    assert fixed["market_factor"] is None and fixed["fixed_deduction"] is None and fixed["fixed_addition"] is None
    spot = row_values(by_label(rows, "Feed Spot"), Basis.NET, TODAY).values
    assert spot["remuneration"] is None
    assert spot["market_factor"] == pytest.approx(10.0)
    assert spot["fixed_deduction"] == 0.5 and spot["fixed_addition"] == 0.25


def test_gross_and_net_on_one_basis(catalog):
    rows = build_rows(IMPORT, USER, catalog)
    gross_stored, net_stored = by_label(rows, "Fix Gross"), by_label(rows, "My Fix")
    assert row_values(gross_stored, Basis.NET, TODAY).values["base_price"] == pytest.approx(20.0)
    assert row_values(gross_stored, Basis.NET, TODAY).values["monthly_fee"] == pytest.approx(3.5)
    assert row_values(net_stored, Basis.GROSS, TODAY).values["base_price"] == pytest.approx(30.0)
    assert row_values(net_stored, Basis.NET, TODAY).values["base_price"] == 25.0
    spot = row_values(by_label(rows, "Spot Net"), Basis.GROSS, TODAY).values
    assert spot["markup_cent"] == pytest.approx(1.8) and spot["price_cap"] == pytest.approx(48.0)
    assert spot["markup_percent"] == 2.0  # a percentage is no price
    assert on_basis(None, gross_stored.tariff, Basis.NET) is None
    with pytest.raises(ValueError, match="basis"):
        on_basis(1.0, gross_stored.tariff, "half")  # type: ignore[arg-type]


def test_monthly_table_shows_this_month_or_stays_empty(catalog):
    rows = build_rows(IMPORT, USER, catalog)
    now = row_values(by_label(rows, "Monthly Now"), Basis.GROSS, TODAY)
    assert now.values["base_price"] == 12.0 and not now.month_missing
    old = row_values(by_label(rows, "Monthly Old"), Basis.GROSS, TODAY)
    assert old.values["base_price"] is None and old.month_missing  # no fallback to October
    assert month_value(by_label(rows, "Monthly Old").tariff, date(2026, 10, 3)) == 11.0
    with pytest.raises(ValueError, match="monthly"):
        month_value(by_label(rows, "Fix Gross").tariff, TODAY)


def test_filter_by_land_kind_origin_and_text(catalog):
    rows = build_rows(IMPORT, USER, catalog)
    labels = lambda chosen: [row.tariff.label for row in filter_rows(rows, chosen)]
    assert "Germany Fix" not in labels(OverviewFilter(land="AT", region_only=False))
    assert "My Fix" in labels(OverviewFilter(land="AT", region_only=False))  # no land: no restriction
    assert labels(OverviewFilter(land="DE", region_only=False)) == ["My Fix", "Germany Fix"]
    assert labels(OverviewFilter(kind="spot:60min", region_only=False)) == ["Spot Net"]
    assert labels(OverviewFilter(kind="monthly", region_only=False)) == ["Monthly Now", "Monthly Old"]
    assert labels(OverviewFilter(origin=Origin.OWN, region_only=False)) == ["My Fix"]
    assert labels(OverviewFilter(text="  gross ", region_only=False)) == ["Fix Gross"]
    assert labels(OverviewFilter(text="SUPPLIER_DE", region_only=False)) == ["Germany Fix"]
    assert lands_of(rows) == ["AT", "DE"]
    assert kinds_of(rows) == ["fixed", "spot:60min", "monthly"]


def test_my_region_only(catalog):
    rows = build_rows(IMPORT, USER, catalog)
    labels = lambda chosen: [row.tariff.label for row in filter_rows(rows, chosen)]
    assert "Vienna Only" not in labels(OverviewFilter(house_land="AT", house_region="8"))
    assert "Vienna Only" in labels(OverviewFilter(house_land="AT", house_region="9"))
    assert "Vienna Only" in labels(OverviewFilter(house_land="AT", house_region="8", region_only=False))
    assert "Vienna Only" in labels(OverviewFilter(house_land="AT", house_region=None))  # no house region: not checked


def test_invalid_or_unsupported_entries_fail_loud(catalog):
    broken = {"import_tariffs": [{**USER["import_tariffs"][0], "tiers": []}]}
    with pytest.raises(EdibertError) as caught:
        build_rows(IMPORT, broken, catalog)
    assert caught.value.code == ErrorCode.UNSUPPORTED_FEATURE
    unknown = {"import_tariffs": [{**USER["import_tariffs"][0], "colour": "red"}]}
    with pytest.raises(EdibertError) as caught:
        build_rows(IMPORT, unknown, catalog)
    assert caught.value.code == ErrorCode.TARIFF_UNKNOWN_FIELD
