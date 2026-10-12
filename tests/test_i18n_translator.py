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
    with pytest.raises(MissingTranslationError):
        Translator("en").t("does.not.exist")


def test_missing_parameter_is_an_error():
    with pytest.raises(MissingTranslationError):
        Translator("en").t("warning.rule_shadowed", rule="x")


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
