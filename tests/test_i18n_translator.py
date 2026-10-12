import logging

import pytest

from edbert.errors import EdbertError, ErrorCode
from edbert.i18n import MissingTranslationError, Translator


def test_translates_with_parameters():
    de = Translator("de")
    en = Translator("en")
    assert de.t("editor.step.time_windows") == "Zeitfenster"
    assert en.t("editor.step.time_windows") == "Time windows"
    assert "Nacht" in de.t("warning.rule_shadowed", rule="Nacht", by="Wochenende")


def test_unknown_language_fails_loudly():
    with pytest.raises(ValueError):
        Translator("fr")


def test_missing_key_in_english_is_an_error():
    translator = Translator("en")
    with pytest.raises(MissingTranslationError):
        translator.t("does.not.exist")


def test_missing_parameter_is_an_error():
    translator = Translator("en")
    with pytest.raises(MissingTranslationError):
        translator.t("warning.rule_shadowed", rule="x")


def test_missing_key_in_other_language_falls_back_to_english_and_logs(caplog):
    catalogs = {"en": {"only.en": "English text"}, "de": {}}
    translator = Translator("de", catalogs=catalogs)
    with caplog.at_level(logging.WARNING, logger="edbert.i18n"):
        assert translator.t("only.en") == "English text"
    assert "only.en" in caplog.text


def test_error_is_localized_by_code():
    err = EdbertError(
        ErrorCode.UNSUPPORTED_FEATURE,
        "Unsupported feature 'tiers' in tariff 'user_x'.",
        feature="tiers",
        tariff_id="user_x",
    )
    assert "tiers" in Translator("de").error(err)
    assert Translator("de").error(err) != Translator("en").error(err)
    assert str(err).startswith("Unsupported feature")


def test_field_names_in_errors_are_readable_but_unknown_ones_stay():
    missing = EdbertError(ErrorCode.FIELD_MISSING, "x", field="label")
    nested = EdbertError(ErrorCode.VALUE_INVALID, "x", field="user_x.rules[night].time.from", value="25:00")
    odd = EdbertError(ErrorCode.VALUE_INVALID, "x", field="--at", value="tomorrow")
    assert Translator("de").error(missing) == "Pflichtfeld „Name“ fehlt."
    assert "„Von“" in Translator("de").error(nested)
    assert "field \"from\"" in Translator("en").error(nested)
    assert "„--at“" in Translator("de").error(odd)
    assert missing.params["field"] == "label"  # the coded parameter itself is not changed
