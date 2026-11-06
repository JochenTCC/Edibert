import pytest

from edibert.ui.number_columns import localized_number_column


def _config(column) -> dict:
    return column["type_config"]


def test_format_is_localized_and_digits_stay_open_by_default():
    column = localized_number_column()
    assert _config(column)["format"] == "localized"
    assert _config(column).get("step") is None


def test_decimals_set_the_step():
    column = localized_number_column("kWh", decimals=2)
    assert column["label"] == "kWh"
    assert _config(column)["step"] == pytest.approx(0.01)


def test_decimals_and_step_together_fail_loudly():
    with pytest.raises(ValueError):
        localized_number_column(decimals=2, step=0.5)
