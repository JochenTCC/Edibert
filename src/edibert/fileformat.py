"""The tariff-format version track: the ``tariff_format`` root key of every tariff file, and atomic JSON writes.

All four tariff-track files share one version (``TARIFF_FORMAT``). A file without the key or with a version
this release does not know is an error; old files are brought forward by :mod:`edibert.migration`.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from edibert.errors import EdibertError, ErrorCode

FORMAT_KEY = "tariff_format"
TARIFF_FORMAT = 1  # current version, written into every new or migrated file
SUPPORTED_TARIFF_FORMATS = (1,)
CATALOG_FILE = "tariffs.json"
USER_FILE = "user_tariffs.json"
GRID_CATALOG_FILE = "grid_fees.json"
USER_GRID_FILE = "user_grid_fees.json"
TARIFF_TRACK_FILES = (CATALOG_FILE, USER_FILE, GRID_CATALOG_FILE, USER_GRID_FILE)


def check_tariff_format(document: Mapping[str, Any], where: str) -> int:
    """The document's ``tariff_format``; missing is ``FORMAT_MISSING``, unknown is ``FORMAT_UNSUPPORTED``."""
    if FORMAT_KEY not in document:
        raise EdibertError(
            ErrorCode.FORMAT_MISSING, f"'{where}' has no '{FORMAT_KEY}'; migrate the file first.", path=where
        )
    value = document[FORMAT_KEY]
    if isinstance(value, bool) or not isinstance(value, int) or value not in SUPPORTED_TARIFF_FORMATS:
        supported = ", ".join(str(item) for item in SUPPORTED_TARIFF_FORMATS)
        raise EdibertError(
            ErrorCode.FORMAT_UNSUPPORTED,
            f"'{where}' has {FORMAT_KEY} {value!r}; this release reads {supported}.",
            path=where,
            value=value,
            supported=supported,
        )
    return value


def write_json_atomic(path: Path, document: Mapping[str, Any]) -> None:
    """Write UTF-8 JSON through a temporary file, so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
