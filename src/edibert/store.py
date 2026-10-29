"""Loading tariff documents: the catalog (``tariffs.json``) and the user file (``user_tariffs.json``)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edibert._fields import as_dict, check_known, invalid
from edibert.errors import EdibertError, ErrorCode
from edibert.fileformat import FORMAT_KEY, check_tariff_format
from edibert.tariff import EXPORT, IMPORT, Tariff, parse_tariff, with_periods

USER_PREFIX = "user_"

# Root keys of a tariff file. Besides the two lists and the format version these are maintenance data of
# the Earnie catalog, ignored here. ``earnie_data_model`` is not one of them: only the migration reads it.
ROOT_FIELDS = (
    "import_tariffs", "export_tariffs", FORMAT_KEY, "catalog_as_of", "user_tariffs_as_of",
    "oemag_monthly_feed_in_rates", "monthly_float_reference_cent_kwh",
    "econtrol_referenzmarktwert_pv_monthly", "$schema", "package",
)  # fmt: skip


@dataclass
class TariffSet:
    """All tariffs by direction and ID, with their origin (``catalog`` or ``user``)."""

    imports: dict[str, Tariff] = field(default_factory=dict)
    exports: dict[str, Tariff] = field(default_factory=dict)
    origin: dict[tuple[str, str], str] = field(default_factory=dict)

    def get(self, direction: str, tariff_id: str) -> Tariff:
        table = self.imports if direction == IMPORT else self.exports
        if tariff_id not in table:
            raise invalid(f"{direction}_tariff_id", tariff_id)
        return table[tariff_id]


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read tariff file '{path}': {exc}", path=str(path)) from exc
    return as_dict(data, str(path))


def _check_prefix(tariff_id: str, origin: str) -> None:
    if origin == "user" and not tariff_id.startswith(USER_PREFIX):
        raise EdibertError(
            ErrorCode.ID_PREFIX_MISSING,
            f"User tariff ID '{tariff_id}' must start with '{USER_PREFIX}'.",
            tariff_id=tariff_id,
        )
    if origin == "catalog" and tariff_id.startswith(USER_PREFIX):
        raise EdibertError(
            ErrorCode.ID_PREFIX_RESERVED,
            f"Catalog tariff ID '{tariff_id}' uses the reserved prefix '{USER_PREFIX}'.",
            tariff_id=tariff_id,
        )


def _add_section(result: TariffSet, raw_list: object, direction: str, origin: str, where: str) -> None:
    if raw_list is None:
        return
    if not isinstance(raw_list, list):
        raise invalid(where, raw_list)
    table = result.imports if direction == IMPORT else result.exports
    versions: dict[str, list[Tariff]] = {}
    for raw in raw_list:
        tariff = parse_tariff(raw, direction)
        _check_prefix(tariff.id, origin)
        if tariff.id in table:  # already loaded from the other file
            raise EdibertError(
                ErrorCode.ID_COLLISION, f"Duplicate {direction} tariff ID '{tariff.id}'.", tariff_id=tariff.id
            )
        versions.setdefault(tariff.id, []).append(tariff)
    for tariff_id, entries in versions.items():
        # Several entries of one ID are validity versions: only in the catalog (the tariff database writes
        # them) and only when each states where it starts; anything else is a plain duplicate.
        if len(entries) > 1 and (origin != "catalog" or any(entry.valid_from is None for entry in entries)):
            raise EdibertError(
                ErrorCode.ID_COLLISION, f"Duplicate {direction} tariff ID '{tariff_id}'.", tariff_id=tariff_id
            )
        table[tariff_id] = entries[0] if len(entries) == 1 else with_periods(entries)
        result.origin[(direction, tariff_id)] = origin


def _add_document(result: TariffSet, document: Mapping[str, Any], origin: str, where: str) -> None:
    check_tariff_format(document, where)
    check_known(document, ROOT_FIELDS, where)
    _add_section(result, document.get("import_tariffs"), IMPORT, origin, f"{where}.import_tariffs")
    _add_section(result, document.get("export_tariffs"), EXPORT, origin, f"{where}.export_tariffs")


def parse_tariff_documents(
    catalog: Mapping[str, Any] | None,
    user: Mapping[str, Any] | None,
    where: tuple[str, str] = ("tariffs.json", "user_tariffs.json"),
) -> TariffSet:
    """Catalog and user document (already read, either may be ``None``) as one set, checked like files."""
    result = TariffSet()
    if catalog is not None:
        _add_document(result, as_dict(catalog, where[0]), "catalog", where[0])
    if user is not None:
        _add_document(result, as_dict(user, where[1]), "user", where[1])
    return result


def load_tariffs(catalog: Path | None = None, user: Path | None = None) -> TariffSet:
    """Load the catalog and the user file (optional, may not exist) into one set.

    Both files need a supported ``tariff_format``. The same ID in both files is an error, as is a wrong
    ID prefix; nothing is overridden silently.
    """
    catalog_doc = _read_json(catalog) if catalog is not None else None
    user_doc = _read_json(user) if user is not None and user.exists() else None
    return parse_tariff_documents(catalog_doc, user_doc, (str(catalog), str(user)))


def load_tariff_file(path: Path, direction: str) -> Tariff:
    """Load a single tariff object (as in ``examples/``)."""
    return parse_tariff(_read_json(path), direction)
