"""Regression: a gross tariff added the net grid fee without VAT (Edibert priced 38 ct where Earnie prices 39.6 ct).

The grid fee is always net. Earnie (``grid_fee_on_tariff_basis``) puts the VAT on it for gross tariffs; Edibert
did not until 0.1.i.
"""

import pytest
from conftest import at, flat_grid_fee, make

from edibert.series import tariff_price_series
from edibert.tariff import EXPORT, evaluate, price_cent

GROSS = {"id": "g", "type": "fixed_cent", "supplier_id": "s", "fix_cent_kwh": 30.0, "prices_include_vat": True, "vat_percent": 20}
NET = {**GROSS, "id": "n", "prices_include_vat": False}
NOON = "2026-10-12 12:00"


def test_gross_tariff_puts_the_vat_on_the_grid_fee_only(ctx_plain):
    result = evaluate(make(GROSS), at(NOON), ctx_plain, grid_fee=flat_grid_fee(8.0))
    assert result.grid_cent == 8.0  # stays net
    assert result.cent == pytest.approx(30.0 + 8.0 * 1.2)  # 39.6, not 38.0


def test_net_tariff_puts_the_vat_on_the_whole_sum(ctx_plain):
    assert price_cent(make(NET), at(NOON), ctx_plain, grid_fee=flat_grid_fee(8.0)) == pytest.approx((30.0 + 8.0) * 1.2)


def test_without_grid_fee_and_for_exports_nothing_changes(ctx_plain):
    assert price_cent(make(GROSS), at(NOON), ctx_plain) == 30.0
    export = make({"id": "e", "type": "fixed", "supplier_id": "s", "k_push_cent": 5.0, "vat_percent": 20}, EXPORT)
    assert price_cent(export, at(NOON), ctx_plain, grid_fee=flat_grid_fee(8.0)) == 5.0


def test_series_shows_the_vat_on_the_grid_fee_of_a_gross_tariff(ctx_plain):
    series = tariff_price_series(make(GROSS), ctx_plain, at("2026-10-12 12:00"), at("2026-10-12 13:00"), resolution_min=60, grid_fee=flat_grid_fee(8.0))
    point = series.points[0]
    assert (point.supplier_cent, point.grid_cent, point.vat_cent, point.cent) == (30.0, 8.0, 1.6, 39.6)
