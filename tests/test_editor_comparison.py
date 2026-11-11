"""Comparison data and template rows of the tariff overview (Editor P4c)."""

from datetime import date

import pytest

from edibert.context import PricingContext
from edibert.editor.comparison import TooManyToCompare, day_curves, parameter_lines
from edibert.editor.overview import Basis, Origin, build_rows, row_values, template_row
from edibert.errors import ErrorCode, WarningCode
from edibert.exchange import Template
from edibert.tariff import EXPORT, IMPORT

TODAY = date(2026, 11, 11)
HOUSE = PricingContext("Europe/Vienna", "AT", "9")
NO_REGION = PricingContext("Europe/Vienna", "AT", None)


def entry(tariff_id: str, label: str, tariff_type: str = "fixed_cent", **extra) -> dict:
    """A placeholder tariff (no real supplier data)."""
    return {"id": tariff_id, "label": label, "type": tariff_type, "land": "AT", "supplier_id": "s_demo", "vat_percent": 20, **extra}


def own_rows(*raws: dict, direction: str = IMPORT):
    return build_rows(direction, {"tariff_format": 1, f"{direction}_tariffs": list(raws)})


@pytest.fixture
def rows():
    return own_rows(
        entry("user_a", "A", fix_cent_kwh=24.0, monthly_fee_eur=3.0),
        entry("user_b", "B", fix_cent_kwh=20.0, prices_include_vat=False, monthly_fee_eur=2.5),
        entry("user_c", "C", "spot_hourly", markup_percent=2.0, settlement_fee_cent_kwh=1.0, prices_include_vat=False),
    )


def line(lines, column_id):
    (found,) = [item for item in lines if item.column.id == column_id]
    return found


def test_parameters_line_up_and_mark_differences(rows):
    lines = parameter_lines(rows, Basis.GROSS, TODAY)
    assert "label" not in [item.column.id for item in lines]  # the label heads the columns
    assert line(lines, "supplier").values == ("s_demo",) * 3 and not line(lines, "supplier").differs
    assert line(lines, "kind").values == ("fixed", "fixed", "spot:15min") and line(lines, "kind").differs
    base = line(lines, "base_price")
    assert base.values == (24.0, pytest.approx(24.0), None)


def test_equal_prices_on_another_basis_do_not_differ(rows):
    a, b, _spot = rows
    # A: 24.0 gross; B: 20.0 net = 24.0 gross. Fees: 3.0 gross vs 2.5 net = 3.0 gross
    gross = parameter_lines([a, b], Basis.GROSS, TODAY)
    assert not line(gross, "base_price").differs and not line(gross, "monthly_fee").differs
    net = parameter_lines([a, b], Basis.NET, TODAY)
    assert line(net, "base_price").values == (pytest.approx(20.0), 20.0)
    assert not line(net, "base_price").differs


def test_the_values_are_those_of_the_table(rows):
    lines = parameter_lines(rows, Basis.NET, TODAY)
    for index, row in enumerate(rows):
        cells = row_values(row, Basis.NET, TODAY).values
        assert all(item.values[index] == cells[item.column.id] for item in lines)


def test_more_than_five_or_none_is_refused():
    six = own_rows(*(entry(f"user_{n}", f"T{n}", fix_cent_kwh=20.0 + n) for n in range(6)))
    with pytest.raises(TooManyToCompare):
        parameter_lines(six, Basis.GROSS, TODAY)
    with pytest.raises(TooManyToCompare):
        day_curves(six, HOUSE, None, 2026, 11, "weekday", Basis.GROSS)
    assert len(parameter_lines(six[:5], Basis.GROSS, TODAY)) > 0  # five is fine
    with pytest.raises(ValueError, match="Nothing"):
        parameter_lines([], Basis.GROSS, TODAY)


def test_one_direction_per_comparison(rows):
    export = own_rows(entry("user_e", "E", "fixed", k_push_cent=8.0), direction=EXPORT)
    with pytest.raises(ValueError, match="one direction"):
        parameter_lines([rows[0], export[0]], Basis.GROSS, TODAY)


def test_day_curves_per_tariff_and_basis(rows):
    gross = day_curves(rows, HOUSE, None, 2026, 11, "weekday", Basis.GROSS)
    assert {point.row_key for point in gross.points} == {"own:user_a", "own:user_b", "own:user_c"}
    assert not gross.gaps
    a_points = [point for point in gross.points if point.row_key == "own:user_a"]
    assert len(a_points) == 96 and {point.cent for point in a_points} == {24.0}
    b_gross = {point.cent for point in gross.points if point.row_key == "own:user_b"}
    assert b_gross == {24.0}  # 20 net plus 20 % VAT
    net = day_curves(rows, HOUSE, None, 2026, 11, "weekday", Basis.NET)
    assert {point.cent for point in net.points if point.row_key == "own:user_a"} == {20.0}
    spot = sorted(point.cent for point in net.points if point.row_key == "own:user_c")
    assert spot[0] < spot[-1]  # the example market curve moves over the day
    with pytest.raises(ValueError, match="day type"):
        day_curves(rows, HOUSE, None, 2026, 11, "monday", Basis.GROSS)


def test_a_missing_day_type_is_a_gap_with_its_reason(rows):
    no_calendar = day_curves(rows[:1], NO_REGION, None, 2026, 11, "holiday", Basis.GROSS)
    assert [(gap.row_key, gap.reason) for gap in no_calendar.gaps] == [("own:user_a", "no_calendar")]
    assert not no_calendar.points
    march = day_curves(rows[:1], HOUSE, None, 2026, 3, "holiday", Basis.GROSS)  # no public holiday in Vienna in March 2026
    assert [gap.reason for gap in march.gaps] == ["no_holiday"]
    november = day_curves(rows[:1], HOUSE, None, 2026, 11, "holiday", Basis.GROSS)  # 1 November
    assert not november.gaps and november.points


def test_a_pricing_error_is_a_gap_and_a_fallback_month_is_noted():
    rates = [{"year": 2025, "month": 11, "tariff_cent_kwh": 11.0}]
    rows = own_rows(entry("user_m", "Monthly", "monthly_table", monthly_rates=rates),
                    entry("user_v", "Ended", fix_cent_kwh=20.0, valid_to="2026-06-30"))  # fmt: skip
    curves = day_curves(rows, HOUSE, None, 2026, 11, "weekday", Basis.GROSS)
    assert [(row_key, note.code) for row_key, note in curves.notes] == [("own:user_m", WarningCode.MONTH_RATE_FALLBACK)]
    (gap,) = curves.gaps
    assert (gap.row_key, gap.reason, gap.error.code) == ("own:user_v", "error", ErrorCode.TARIFF_NOT_VALID)
    missing = day_curves(rows[:1], HOUSE, None, 2026, 6, "weekday", Basis.GROSS)  # no June rate, no fallback either
    assert missing.gaps[0].error.code == ErrorCode.PRICE_MISSING


def template(local_id: str = "shared_abc", *, check_state: str = "unchecked", reliable: bool = True, checked: str | None = None,
             direction: str = IMPORT, **tariff) -> Template:  # fmt: skip
    payload = {"label": "Shared", "type": "fixed_cent", "supplier_id": "user_sun", "land": "AT", "fix_cent_kwh": 19.5,
               "vat_percent": 20, **tariff}  # fmt: skip
    return Template(f"AT/{direction}/{local_id}", "a" * 64, direction, payload, None, check_state, reliable, 2, None, checked)


def test_template_rows_carry_reference_trust_and_checked_hint():
    row = template_row(template(checked="b" * 64))
    assert (row.origin, row.key, row.tariff.id) == (Origin.TEMPLATE, "template:shared_abc", "shared_abc")
    assert row.db_ref.to_dict() == {"id": "AT/import/shared_abc", "version": "a" * 64}
    assert row.trust == "reliable" and row.checked_version_exists
    assert row_values(row, Basis.GROSS, TODAY).values["check"] == "reliable"
    assert template_row(template(check_state="checked")).trust == "checked"
    assert not template_row(template()).checked_version_exists


def test_template_rows_join_their_direction_only():
    templates = [template_row(template()), template_row(template("shared_feed", direction=EXPORT, type="fixed", k_push_cent=7.0))]
    rows = build_rows(IMPORT, {"tariff_format": 1, "import_tariffs": [entry("user_a", "A", fix_cent_kwh=24.0)]}, (), templates)
    assert [row.key for row in rows] == ["own:user_a", "template:shared_abc"]
    with pytest.raises(ValueError, match="as template"):
        build_rows(IMPORT, {}, (), rows[:1])


def test_an_invalid_template_fails_loud():
    from edibert.errors import EdibertError

    with pytest.raises(EdibertError) as caught:
        template_row(template(tiers=[]))
    assert caught.value.code == ErrorCode.UNSUPPORTED_FEATURE
    bad = Template("shared_abc", "a" * 64, IMPORT, {}, None, "unchecked", False, 0, None, None)
    with pytest.raises(ValueError, match="land>/<direction>"):
        template_row(bad)
