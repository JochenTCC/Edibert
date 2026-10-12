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
from functools import cache
from importlib import resources

from edbert.errors import EdbertError, EdbertWarning

SOURCE_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "de")

logger = logging.getLogger(__name__)


class MissingTranslationError(KeyError):
    """A key is missing in the authoritative (English) catalog, or a placeholder is missing."""


@cache
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

    def number(self, value: float, decimals: int = 4) -> str:
        """Number with at least two and at most ``decimals`` decimals, decimal comma in German."""
        text = f"{value:.{decimals}f}".rstrip("0")
        whole, _, frac = text.partition(".")
        text = f"{whole}.{frac.ljust(2, '0')}"
        return text.replace(".", ",") if self.language == "de" else text

    def field_name(self, path: str) -> str:
        """Readable name of a field path: ``user_x.rules[night].time.from`` -> "Von". Unknown names stay as they are."""
        last = path.rsplit(".", 1)[-1].split("[", 1)[0]
        known = self._catalog.get(f"field.{last}") or self._source.get(f"field.{last}")
        return known if known else path

    def error(self, err: EdbertError) -> str:
        """Localized text for a coded error. A ``field`` parameter is shown by its readable name."""
        params = dict(err.params)
        if isinstance(params.get("field"), str):
            params["field"] = self.field_name(params["field"])
        return self.t(f"error.{err.code.value}", **params)

    def warning(self, warning: EdbertWarning) -> str:
        """Localized text for a warning; a ``requirement`` parameter is translated as well."""
        params = dict(warning.params)
        if "requirement" in params:
            params["requirement"] = self.t(f"requirement.{params['requirement']}")
        return self.t(f"warning.{warning.code.value}", **params)
