"""Loading tariff documents: the catalog (``tariffs.json``) and the user file (``user_tariffs.json``)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edbert._fields import as_dict, check_known, invalid
from edbert.errors import EdbertError, ErrorCode
from edbert.tariff import EXPORT, IMPORT, Tariff, parse_tariff

USER_PREFIX = "user_"

# Root keys of the Earnie catalog that are maintenance data, not tariffs. Ignored here.
ROOT_FIELDS = (
    "import_tariffs", "export_tariffs", "catalog_as_of", "user_tariffs_as_of", "earnie_data_model",
    "oemag_monthly_feed_in_rates", "monthly_float_reference_cent_kwh",
    "econtrol_referenzmarktwert_pv_monthly", "$schema",
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
        raise EdbertError(ErrorCode.FILE_INVALID, f"Cannot read tariff file '{path}': {exc}", path=str(path)) from exc
    return as_dict(data, str(path))


def _check_prefix(tariff_id: str, origin: str) -> None:
    if origin == "user" and not tariff_id.startswith(USER_PREFIX):
        raise EdbertError(
            ErrorCode.ID_PREFIX_MISSING,
            f"User tariff ID '{tariff_id}' must start with '{USER_PREFIX}'.",
            tariff_id=tariff_id,
        )
    if origin == "catalog" and tariff_id.startswith(USER_PREFIX):
        raise EdbertError(
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
    for raw in raw_list:
        tariff = parse_tariff(raw, direction)
        _check_prefix(tariff.id, origin)
        if tariff.id in table:
            raise EdbertError(
                ErrorCode.ID_COLLISION, f"Duplicate {direction} tariff ID '{tariff.id}'.", tariff_id=tariff.id
            )
        table[tariff.id] = tariff
        result.origin[(direction, tariff.id)] = origin


def _add_file(result: TariffSet, path: Path, origin: str) -> None:
    document = _read_json(path)
    check_known(document, ROOT_FIELDS, str(path))
    _add_section(result, document.get("import_tariffs"), IMPORT, origin, f"{path}.import_tariffs")
    _add_section(result, document.get("export_tariffs"), EXPORT, origin, f"{path}.export_tariffs")


def load_tariffs(catalog: Path | None = None, user: Path | None = None) -> TariffSet:
    """Load the catalog and the user file (optional, may not exist) into one set.

    The same ID in both files is an error, as is a wrong ID prefix; nothing is overridden silently.
    """
    result = TariffSet()
    if catalog is not None:
        _add_file(result, catalog, "catalog")
    if user is not None and user.exists():
        _add_file(result, user, "user")
    return result


def load_tariff_file(path: Path, direction: str) -> Tariff:
    """Load a single tariff object (as in ``examples/``)."""
    return parse_tariff(_read_json(path), direction)
