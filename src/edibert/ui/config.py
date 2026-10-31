"""UI configuration: from environment variables (``python -m edibert ui``) or built by a host page."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from edibert.context import PricingContext
from edibert.gridfee import GridFee
from edibert.i18n import SOURCE_LANGUAGE, SUPPORTED_LANGUAGES

if TYPE_CHECKING:
    from edibert.contribution import ContributionTransport
    from edibert.exchange import ExchangeClient

ENV_DATA_DIR = "EDIBERT_DATA_DIR"
ENV_CATALOG = "EDIBERT_CATALOG"
ENV_LANG = "EDIBERT_LANG"


@dataclass(frozen=True)
class HostHouse:
    """House facts a host application supplies. The editor shows them read-only and keeps no ``house.json``."""

    context: PricingContext
    grid_fee: GridFee | None
    capabilities: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class UiConfig:
    """Where the editor reads and writes, and what a host page hooks into.

    ``delete_guard(direction, tariff_id)``: a warning text when deleting that user tariff needs a
    confirmation (e.g. the host's scenarios that use it), or ``None`` to delete right away.
    ``on_change(action, direction, tariff_id)``: called after the editor wrote ``user_tariffs.json``
    (``action`` is ``"save"`` or ``"delete"``), before the page reruns.
    ``contribution_transport``: sends shared tariffs to the tariff database; ``None`` = no endpoint configured,
    sharing is off and the share section says so.
    ``exchange``: client of the tariff database server for the package download and the status of a copied
    tariff; ``None`` = both are off and the editor says so.
    """

    data_dir: Path
    catalog: Path | None
    language: str
    key_prefix: str = ""
    host_house: HostHouse | None = None
    delete_guard: Callable[[str, str], str | None] | None = None
    on_change: Callable[[str, str, str], None] | None = None
    contribution_transport: ContributionTransport | None = None
    exchange: ExchangeClient | None = None

    @property
    def user_file(self) -> Path:
        return self.data_dir / "user_tariffs.json"

    @property
    def house_file(self) -> Path:
        return self.data_dir / "house.json"


def check_language(language: str, source: str) -> str:
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"{source}='{language}' is not supported. Supported: {', '.join(SUPPORTED_LANGUAGES)}.")
    return language


def config_from_env() -> UiConfig:
    """Data folder (default ``./edibert_data``), optional catalog file, start language, and the client of the
    tariff database server with its share transport (both off with ``EDIBERT_EXCHANGE_OFF=1``)."""
    from edibert.exchange import (
        ExchangeClient,
        ServerTransport,
        exchange_config_from_env,
    )

    language = check_language(os.environ.get(ENV_LANG, SOURCE_LANGUAGE), ENV_LANG)
    catalog = os.environ.get(ENV_CATALOG)
    settings = exchange_config_from_env()
    client = None if settings is None else ExchangeClient(settings)
    transport = None if client is None else ServerTransport(client)
    return UiConfig(Path(os.environ.get(ENV_DATA_DIR, "edibert_data")), Path(catalog) if catalog else None, language,
                    contribution_transport=transport, exchange=client)  # fmt: skip
