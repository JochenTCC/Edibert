"""Decimal separator and number text per UI language, shared with hosts such as Earnie.

No Streamlit and no global state: the caller passes the language. Units stay with the caller
(catalog texts in Edibert, the host's own wording elsewhere).
"""

from __future__ import annotations

# One entry per language in ``edibert.i18n.SUPPORTED_LANGUAGES`` (checked by the tests).
DECIMAL_SEPARATORS = {"en": ".", "de": ","}
_THOUSANDS_SEPARATORS = {"en": ",", "de": "."}


def decimal_separator(language: str) -> str:
    """``.`` or ``,`` for ``language``; fail loudly for unsupported languages."""
    try:
        return DECIMAL_SEPARATORS[language]
    except KeyError:
        raise ValueError(
            f"Unsupported language '{language}'. Supported: {', '.join(DECIMAL_SEPARATORS)}."
        ) from None


def format_fixed(value: float, decimals: int, language: str, *, signed: bool = False) -> str:
    """``value`` with exactly ``decimals`` decimals; ``signed`` writes ``+`` for positive values."""
    separator = decimal_separator(language)
    text = f"{value:+.{decimals}f}" if signed else f"{value:.{decimals}f}"
    return text if separator == "." else text.replace(".", separator)


def format_general(value: float, language: str) -> str:
    """``value`` as ``:g`` writes it (no trailing zeros), with the separator of ``language``."""
    separator = decimal_separator(language)
    text = f"{value:g}"
    return text if separator == "." else text.replace(".", separator)


def plotly_separators(language: str) -> str:
    """Plotly ``layout.separators``: the decimal mark, then the thousands mark."""
    return decimal_separator(language) + _THOUSANDS_SEPARATORS[language]


def language_from_accept_language(header: str | None) -> str | None:
    """The supported language the browser prefers most, from an ``Accept-Language`` header.

    Entries are ranked by their ``q`` weight (ties keep the header order); region tags count for
    their language (``de-AT`` -> ``de``). ``None`` when the header names no supported language: the
    host decides what then applies.
    """
    if not header:
        return None
    ranked: list[tuple[float, int, str]] = []
    for position, entry in enumerate(header.split(",")):
        tag, _, params = entry.strip().partition(";")
        language = tag.strip().replace("_", "-").split("-", 1)[0].lower()
        if language not in DECIMAL_SEPARATORS:
            continue
        weight = 1.0
        for param in params.split(";"):
            name, _, raw = param.strip().partition("=")
            if name.strip() == "q":
                try:
                    weight = float(raw)
                except ValueError:
                    weight = 0.0
        if weight > 0:
            ranked.append((-weight, position, language))
    return min(ranked)[2] if ranked else None
