"""UI configuration from environment variables (set by ``python -m edibert ui``)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from edibert.i18n import SOURCE_LANGUAGE, SUPPORTED_LANGUAGES

ENV_DATA_DIR = "EDIBERT_DATA_DIR"
ENV_CATALOG = "EDIBERT_CATALOG"
ENV_LANG = "EDIBERT_LANG"


@dataclass(frozen=True)
class UiConfig:
    data_dir: Path
    catalog: Path | None
    language: str

    @property
    def user_file(self) -> Path:
        return self.data_dir / "user_tariffs.json"

    @property
    def house_file(self) -> Path:
        return self.data_dir / "house.json"


def config_from_env() -> UiConfig:
    """Data folder (default ``./edibert_data``), optional catalog file and start language."""
    language = os.environ.get(ENV_LANG, SOURCE_LANGUAGE)
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"{ENV_LANG}='{language}' is not supported. Supported: {', '.join(SUPPORTED_LANGUAGES)}.")
    catalog = os.environ.get(ENV_CATALOG)
    return UiConfig(Path(os.environ.get(ENV_DATA_DIR, "edibert_data")), Path(catalog) if catalog else None, language)
