import pytest

from edbert.errors import ErrorCode
from edbert.i18n import SOURCE_LANGUAGE, SUPPORTED_LANGUAGES, load_catalog, placeholders

OTHER_LANGUAGES = [lang for lang in SUPPORTED_LANGUAGES if lang != SOURCE_LANGUAGE]


def test_source_language_is_supported():
    assert SOURCE_LANGUAGE in SUPPORTED_LANGUAGES


@pytest.mark.parametrize("language", OTHER_LANGUAGES)
def test_same_keys_as_english(language):
    source = set(load_catalog(SOURCE_LANGUAGE))
    other = set(load_catalog(language))
    assert source - other == set(), f"missing in {language}"
    assert other - source == set(), f"extra in {language} (add to English first)"


@pytest.mark.parametrize("language", OTHER_LANGUAGES)
def test_same_placeholders_as_english(language):
    source = load_catalog(SOURCE_LANGUAGE)
    other = load_catalog(language)
    for key, text in source.items():
        assert placeholders(other[key]) == placeholders(text), f"placeholders differ for {key}"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_no_empty_texts(language):
    for key, text in load_catalog(language).items():
        assert text.strip(), f"empty text for {key} ({language})"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_error_code_has_a_text(language):
    catalog = load_catalog(language)
    for code in ErrorCode:
        assert f"error.{code.value}" in catalog, f"error.{code.value} missing ({language})"
