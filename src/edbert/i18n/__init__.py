"""Translation catalogs and the per-session :class:`Translator`.

English is authoritative. Catalogs are flat JSON files ``catalogs/<lang>.json``
(key -> text with ``{name}`` placeholders). There is no global language state:
create one ``Translator`` per session (Streamlit serves several sessions from one
process).
"""

from __future__ import annotations

import json
import logging
import string
from collections.abc import Mapping
from functools import lru_cache
from importlib import resources

from edbert.errors import EdbertError

SOURCE_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "de")

logger = logging.getLogger(__name__)


class MissingTranslationError(KeyError):
    """A key is missing in the authoritative (English) catalog, or a placeholder is missing."""


@lru_cache(maxsize=None)
def load_catalog(language: str) -> Mapping[str, str]:
    """Load ``catalogs/<language>.json``; fail loudly for unknown languages."""
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(
            f"Unsupported language '{language}'. Supported: {', '.join(SUPPORTED_LANGUAGES)}."
        )
    path = resources.files("edbert.i18n").joinpath("catalogs", f"{language}.json")
    return json.loads(path.read_text(encoding="utf-8"))


def placeholders(text: str) -> frozenset[str]:
    """Names of the ``{placeholders}`` used in ``text``."""
    return frozenset(
        name for _, name, _, _ in string.Formatter().parse(text) if name
    )


class Translator:
    """Translate keys for one language.

    A key missing in the chosen language falls back to English and is logged
    (documented product behavior). A key missing in English is an error.
    """

    def __init__(
        self,
        language: str,
        catalogs: Mapping[str, Mapping[str, str]] | None = None,
    ) -> None:
        if catalogs is None:
            self._catalog = load_catalog(language)
            self._source = load_catalog(SOURCE_LANGUAGE)
        else:
            if language not in catalogs or SOURCE_LANGUAGE not in catalogs:
                raise ValueError(f"catalogs must contain '{language}' and '{SOURCE_LANGUAGE}'.")
            self._catalog = catalogs[language]
            self._source = catalogs[SOURCE_LANGUAGE]
        self.language = language

    def t(self, key: str, **params: object) -> str:
        text = self._catalog.get(key)
        if text is None:
            if key not in self._source:
                raise MissingTranslationError(f"Translation key '{key}' is missing in the English catalog.")
            logger.warning("Translation key '%s' missing for language '%s'; using English.", key, self.language)
            text = self._source[key]
        try:
            return text.format(**params)
        except KeyError as exc:
            raise MissingTranslationError(
                f"Key '{key}' needs parameter {exc} (language '{self.language}')."
            ) from exc

    def error(self, err: EdbertError) -> str:
        """Localized text for a coded error."""
        return self.t(f"error.{err.code.value}", **err.params)
