import pytest

from edibert.i18n import SUPPORTED_LANGUAGES, Translator
from edibert.i18n.numbers import (
    DECIMAL_SEPARATORS,
    decimal_separator,
    format_fixed,
    language_from_accept_language,
    plotly_separators,
)


def test_every_supported_language_has_a_separator():
    assert set(DECIMAL_SEPARATORS) == set(SUPPORTED_LANGUAGES)


def test_unknown_language_fails_loudly():
    with pytest.raises(ValueError):
        decimal_separator("fr")
    with pytest.raises(ValueError):
        format_fixed(1.0, 2, "fr")


@pytest.mark.parametrize(
    ("value", "decimals", "language", "signed", "expected"),
    [
        (12.345, 2, "de", False, "12,35"),
        (12.345, 2, "en", False, "12.35"),
        (0.2, 2, "de", True, "+0,20"),
        (-100.0, 2, "en", True, "-100.00"),
        (-0.1234, 3, "de", True, "-0,123"),
        (1234.5, 1, "de", False, "1234,5"),
    ],
)
def test_format_fixed(value, decimals, language, signed, expected):
    assert format_fixed(value, decimals, language, signed=signed) == expected


def test_plotly_separators():
    assert plotly_separators("de") == ",."
    assert plotly_separators("en") == ".,"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("de-DE,de;q=0.9,en;q=0.8", "de"),
        ("de-AT", "de"),
        ("en-US,en;q=0.9,de;q=0.8", "en"),
        ("EN-gb", "en"),
        ("de_CH", "de"),
        ("fr-FR,fr;q=0.9,en;q=0.8,de;q=0.7", "en"),
        ("en;q=0.5,de;q=0.8", "de"),
        ("de;q=0,en", "en"),
        ("de;q=abc,en;q=0.1", "en"),
        ("fr-FR,ja", None),
        ("*", None),
        ("", None),
        (None, None),
    ],
)
def test_language_from_accept_language(header, expected):
    assert language_from_accept_language(header) == expected


def test_translator_number_uses_the_shared_separator():
    assert Translator("de").number(14.92) == "14,92"
    assert Translator("en").number(14.92) == "14.92"
