"""Cache of the last day-ahead prices, one JSON file per market zone."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from edibert.market.sources import Prices


@dataclass(frozen=True)
class CacheEntry:
    zone: str
    source: str
    fetched_at: datetime  # when the prices were downloaded
    checked_at: datetime  # when the sources were last asked (also if they had nothing new)
    prices: Prices


def cache_path(data_dir: Path, zone: str) -> Path:
    return data_dir / f"market_{zone}.json"


def write_cache(path: Path, entry: CacheEntry) -> None:
    """Atomic write; the cache can always be rebuilt from the sources."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "zone": entry.zone,
        "source": entry.source,
        "fetched_at": entry.fetched_at.isoformat(),
        "checked_at": entry.checked_at.isoformat(),
        "prices": {stamp.isoformat(): cent for stamp, cent in sorted(entry.prices.items())},
    }
    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def read_cache(path: Path) -> CacheEntry | None:
    """The cached prices, ``None`` if there is no file. A damaged file raises ``ValueError``."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        prices = {datetime.fromisoformat(stamp).astimezone(UTC): float(cent) for stamp, cent in data["prices"].items()}
        return CacheEntry(
            zone=str(data["zone"]),
            source=str(data["source"]),
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
            checked_at=datetime.fromisoformat(data["checked_at"]),
            prices=prices,
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"cache '{path}' is unreadable: {exc}") from exc
