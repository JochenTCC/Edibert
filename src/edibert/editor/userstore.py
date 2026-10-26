"""Reading and writing ``user_tariffs.json`` and importing tariffs from files or pasted text."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edibert._fields import as_dict
from edibert.editor.model import slugify
from edibert.errors import EdibertError, ErrorCode
from edibert.store import ROOT_FIELDS, USER_PREFIX
from edibert.tariff import (
    EXPORT,
    IMPORT,
    Tariff,
    parse_tariff,
)

SECTIONS = {IMPORT: "import_tariffs", EXPORT: "export_tariffs"}


def read_document(path: Path) -> dict[str, Any]:
    """The user file as dict; a missing file is an empty document."""
    if not path.exists():
        return {"import_tariffs": [], "export_tariffs": []}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc
    return dict(as_dict(document, str(path)))


def _write_atomic(path: Path, document: Mapping[str, Any]) -> None:
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


def save_user_tariff(path: Path, raw: Mapping[str, Any], direction: str) -> None:
    """Add or replace a tariff (same ID and direction) after validating it; other entries stay untouched."""
    parse_tariff(raw, direction)
    document = read_document(path)
    section = [item for item in document.get(SECTIONS[direction], []) if item.get("id") != raw["id"]]
    section.append(dict(raw))
    document[SECTIONS[direction]] = section
    other = SECTIONS[EXPORT if direction == IMPORT else IMPORT]
    document.setdefault(other, [])
    _write_atomic(path, document)


def delete_user_tariff(path: Path, tariff_id: str, direction: str) -> None:
    document = read_document(path)
    document[SECTIONS[direction]] = [i for i in document.get(SECTIONS[direction], []) if i.get("id") != tariff_id]
    _write_atomic(path, document)


def user_tariff_ids(path: Path) -> dict[str, set[str]]:
    document = read_document(path)
    return {d: {item.get("id", "") for item in document.get(SECTIONS[d], [])} for d in (IMPORT, EXPORT)}


def copy_as_template(raw: Mapping[str, Any], taken: set[str], label_suffix: str) -> dict[str, Any]:
    """Copy a (catalog) tariff as the starting point of an own tariff: new ``user_`` ID, new label."""
    copy = json.loads(json.dumps(raw))
    base = USER_PREFIX + slugify(str(raw.get("id", "tariff")).removeprefix(USER_PREFIX))
    candidate, number = base, 2
    while candidate in taken:
        candidate, number = f"{base}_{number}", number + 1
    copy["id"] = candidate
    copy["label"] = f"{raw.get('label', raw.get('id', ''))} {label_suffix}".strip()
    copy["supplier_id"] = USER_PREFIX + slugify(str(raw.get("supplier_id", "")).removeprefix(USER_PREFIX))
    return copy


@dataclass(frozen=True)
class ImportItem:
    """One tariff found in an import: validated, possibly renamed, possibly clashing with an existing ID."""

    direction: str
    raw: dict[str, Any]
    tariff: Tariff | None
    error: EdibertError | None
    renamed_from: str | None
    collides: bool


def _direction_of(raw: Mapping[str, Any], hint: str) -> str:
    tariff_type = raw.get("type")
    if tariff_type == "fixed":
        return EXPORT
    if tariff_type == "fixed_cent":
        return IMPORT
    return hint


def _item(raw: Mapping[str, Any], direction: str, taken: Mapping[str, set[str]]) -> ImportItem:
    data = dict(raw)
    renamed = None
    tariff_id = str(data.get("id", ""))
    if tariff_id and not tariff_id.startswith(USER_PREFIX):
        renamed, data["id"] = tariff_id, USER_PREFIX + slugify(tariff_id)
    try:
        tariff, error = parse_tariff(data, direction), None
    except EdibertError as err:
        tariff, error = None, err
    return ImportItem(direction, data, tariff, error, renamed, str(data.get("id")) in taken.get(direction, set()))


def parse_import_text(text: str, direction_hint: str, taken: Mapping[str, set[str]]) -> list[ImportItem]:
    """Tariffs from JSON text: a single tariff object or a document with import/export lists.

    A tariff ID without the ``user_`` prefix is renamed (and reported). Nothing is stored here.
    """
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Pasted text is not valid JSON: {exc}", path="(text)") from exc
    document = as_dict(data, "(text)")
    if not any(key in document for key in SECTIONS.values()):
        return [_item(document, _direction_of(document, direction_hint), taken)]
    unknown = [key for key in document if key not in ROOT_FIELDS]
    if unknown:
        raise EdibertError(ErrorCode.TARIFF_UNKNOWN_FIELD, f"Unknown field '{unknown[0]}'.", field=unknown[0])
    items: list[ImportItem] = []
    for direction, section in SECTIONS.items():
        items.extend(_item(entry, direction, taken) for entry in document.get(section, []))
    return items
