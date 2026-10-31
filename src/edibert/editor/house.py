"""House settings of the editor: time zone, location, capabilities, metering and the chosen grid area.

``house.json`` stores the ID of the grid area the house uses (``grid_area_id``): a catalog area of ``grid_fees.json``
or the editor's own area ``user_house`` in ``user_grid_fees.json``; ``null`` means no grid fee. The publisher and the
preview resolve it like Earnie's ``netznutzung``. The own values are edited as a :class:`GridDraft`.

Before ``0.1.d2`` the own grid fee lived in ``house.json`` itself (``grid_enabled``, ``grid_base_cent``,
``grid_rules``). A file with these keys is not read silently: it loads with ``legacy_grid`` set, every grid lookup is
``HOUSE_GRID_LEGACY``, and the migration gate moves the values into ``user_grid_fees.json``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edibert.context import PricingContext
from edibert.editor.model import RuleDraft, unique_rule_ids
from edibert.errors import EdibertError, ErrorCode
from edibert.fileformat import GRID_CATALOG_FILE, USER_GRID_FILE, write_json_atomic
from edibert.gridfee import (
    METERING,
    USER,
    GridFee,
    GridFeeCatalog,
    area_document,
    load_grid_fees,
    parse_grid_fee_catalog,
    parse_grid_fee_config,
    put_user_grid_area,
    resolve_grid_fee,
    user_area_entry,
)
from edibert.rules import REQUIRES

LANDS = ("AT", "DE", "CH")
DEFAULT_TIMEZONE = "Europe/Vienna"
COMMON_TIMEZONES = (DEFAULT_TIMEZONE, "Europe/Berlin", "Europe/Zurich")
HOUSE_GRID_AREA = "user_house"  # the editor's own grid area in ``user_grid_fees.json``
LEGACY_GRID_KEYS = ("grid_enabled", "grid_base_cent", "grid_rules")  # house.json before 0.1.d2
HOUSE_KEYS = ("timezone", "land", "region", "capabilities", "power_metering", "grid_area_id")


@dataclass
class HouseSettings:
    """Where the house is and what it has. Saved next to the user tariffs as ``house.json``."""

    timezone: str = DEFAULT_TIMEZONE
    land: str = "AT"
    region: str = ""
    capabilities: list[str] = field(default_factory=list)
    power_metering: str = METERING[0]  # unmetered_power (households) or metered_power
    grid_area_id: str | None = None  # catalog area, HOUSE_GRID_AREA, or None (no grid fee)
    legacy_grid: dict[str, Any] | None = None  # the pre-0.1.d2 grid keys of the file, until migrated
    path: str = field(default="", compare=False)

    def context(self) -> PricingContext:
        return PricingContext(self.timezone, self.land or None, self.region or None)

    def _check_migrated(self) -> None:
        if self.legacy_grid is not None:
            raise EdibertError(
                ErrorCode.HOUSE_GRID_LEGACY,
                f"'{self.path or 'house.json'}' still holds the own grid fee (grid_enabled, grid_base_cent, grid_rules); "
                "run the migration to move it to user_grid_fees.json.",
                path=self.path or "house.json",
            )

    def grid_fee(self, grids: GridFeeCatalog) -> GridFee | None:
        """The resolved grid fee of the chosen area, or ``None`` when the house has none."""
        self._check_migrated()
        if self.grid_area_id is None:
            return None
        config = parse_grid_fee_config({
            "area_id": self.grid_area_id,
            "power_metering": self.power_metering,
            "quarter_hour_meter": "quarter_hour_meter" in self.capabilities,
        })  # fmt: skip
        return resolve_grid_fee(config, grids)

    def legacy_migration_input(self) -> tuple[list[dict[str, Any]], dict[str, list[Any]], str | None]:
        """What the migration needs from a pre-0.1.d2 ``house.json``: the own area, its rule set and the area the
        house uses (``user_house`` when the own grid fee was switched on, else ``None``)."""
        legacy = self.legacy_grid or {}
        rules = [RuleDraft.from_raw(item) for item in legacy.get("grid_rules") or []]
        base = float(legacy.get("grid_base_cent") or 0.0)
        if not rules and not base and not legacy.get("grid_enabled"):
            return [], {}, None
        area: dict[str, Any] = {"id": HOUSE_GRID_AREA, "land": self.land, "base_cent_kwh": dict.fromkeys(METERING, base)}
        rule_sets: dict[str, list[Any]] = {}
        if rules:
            rule_sets[HOUSE_GRID_AREA] = unique_rule_ids([rule.to_raw(f"grid_rule_{i + 1}") for i, rule in enumerate(rules)])
            area["rule_set"] = HOUSE_GRID_AREA
        return [area], rule_sets, HOUSE_GRID_AREA if legacy.get("grid_enabled") else None

    def migrated(self) -> HouseSettings:
        """The settings after the migration: the legacy keys gone, the own area chosen when it was switched on."""
        _, _, area_id = self.legacy_migration_input()
        result = copy.copy(self)
        result.legacy_grid = None
        result.grid_area_id = area_id
        return result

    def to_json(self) -> dict[str, Any]:
        self._check_migrated()
        return {
            "timezone": self.timezone,
            "land": self.land,
            "region": self.region,
            "capabilities": list(self.capabilities),
            "power_metering": self.power_metering,
            "grid_area_id": self.grid_area_id,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any], path: str = "") -> HouseSettings:
        capabilities = [item for item in data.get("capabilities", []) if item in REQUIRES]
        legacy = {key: data[key] for key in LEGACY_GRID_KEYS if key in data} or None
        metering = str(data.get("power_metering", METERING[0]))
        if metering not in METERING:
            raise EdibertError(ErrorCode.VALUE_INVALID, f"Invalid power_metering {metering!r}.", field="power_metering", value=metering)
        area_id = data.get("grid_area_id")
        if area_id is not None and (not isinstance(area_id, str) or not area_id.strip()):
            raise EdibertError(ErrorCode.VALUE_INVALID, f"Invalid grid_area_id {area_id!r}.", field="grid_area_id", value=area_id)
        return cls(
            timezone=str(data.get("timezone", DEFAULT_TIMEZONE)),
            land=str(data.get("land", "AT")),
            region=str(data.get("region", "")),
            capabilities=capabilities,
            power_metering=metering,
            grid_area_id=area_id,
            legacy_grid=legacy,
            path=path,
        )


def load_house(path: Path) -> HouseSettings:
    """Saved settings, or defaults if there is no file. A broken file is an error."""
    if not path.exists():
        return HouseSettings(path=str(path))
    try:
        return HouseSettings.from_json(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, ValueError, TypeError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc


def save_house(path: Path, house: HouseSettings) -> None:
    write_json_atomic(path, house.to_json())


def grid_catalog_path(catalog: Path | None) -> Path | None:
    """The catalog ``grid_fees.json`` next to ``tariffs.json`` (as a package import writes both)."""
    return None if catalog is None else catalog.parent / GRID_CATALOG_FILE


def load_house_grids(catalog: Path | None, data_dir: Path) -> GridFeeCatalog:
    """Catalog areas (when the catalog folder has a ``grid_fees.json``) and the user areas of ``data_dir``."""
    grid_path = grid_catalog_path(catalog)
    return load_grid_fees(grid_path if grid_path is not None and grid_path.exists() else None, data_dir / USER_GRID_FILE)


# --- own grid values ----------------------------------------------------------------------------------------------


@dataclass
class PartDraft:
    """One component (cent/kWh) or fixed amount (EUR/year) as edited; ``values`` per metering type."""

    id: str = ""
    label: str = ""
    values: dict[str, float | None] = field(default_factory=lambda: dict.fromkeys(METERING, 0.0))
    extra: dict[str, Any] = field(default_factory=dict)
    uid: int = field(default=0, compare=False, repr=False)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any], value_key: str) -> PartDraft:
        value = raw.get(value_key)
        values = dict.fromkeys(METERING, float(value)) if isinstance(value, (int, float)) else dict(value or {})
        known = {"id", "label", value_key}
        return cls(str(raw.get("id", "")), str(raw.get("label", "")), values,
                   {key: item for key, item in raw.items() if key not in known})  # fmt: skip

    def to_raw(self, value_key: str, fallback_id: str) -> dict[str, Any]:
        raw: dict[str, Any] = {"id": self.id or fallback_id}
        if self.label:
            raw["label"] = self.label
        raw[value_key] = dict(self.values)
        raw.update(self.extra)
        return raw


@dataclass
class GridDraft:
    """The own grid area (``user_house``) as edited: work price, rules, components and fixed amounts.

    Fields the editor does not edit (land, regions, operator, source, capacity charges, levy set, ``db_ref``) are kept
    in ``extra`` / ``levies`` as they are, so a catalog copy saved unchanged keeps its database version.
    """

    base: dict[str, float] = field(default_factory=lambda: dict.fromkeys(METERING, 0.0))
    rules: list[RuleDraft] = field(default_factory=list)
    components: list[PartDraft] = field(default_factory=list)
    fixed: list[PartDraft] = field(default_factory=list)
    levies: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_entry(cls, entry: Mapping[str, Any]) -> GridDraft:
        """From an inlined area (``gridfee.area_document``)."""
        area = dict(entry["area"])
        known = {"id", "base_cent_kwh", "rule_set", "levy_set", "components", "fixed_eur_year", "check"}
        return cls(
            base={key: float(value) for key, value in dict(area.get("base_cent_kwh") or {}).items()},
            rules=[RuleDraft.from_raw(item) for item in entry.get("rules") or []],
            components=[PartDraft.from_raw(item, "cent_kwh") for item in area.get("components") or []],
            fixed=[PartDraft.from_raw(item, "eur_year") for item in area.get("fixed_eur_year") or []],
            levies=copy.deepcopy(entry.get("levies")),
            extra={key: copy.deepcopy(value) for key, value in area.items() if key not in known},
        )

    def entry(self) -> dict[str, Any]:
        area: dict[str, Any] = {"id": HOUSE_GRID_AREA, **copy.deepcopy(self.extra), "base_cent_kwh": dict(self.base)}
        if self.components:
            area["components"] = _unique([part.to_raw("cent_kwh", f"component_{i + 1}") for i, part in enumerate(self.components)])
        if self.fixed:
            area["fixed_eur_year"] = _unique([part.to_raw("eur_year", f"fixed_{i + 1}") for i, part in enumerate(self.fixed)])
        rules = unique_rule_ids([rule.to_raw(f"grid_rule_{i + 1}") for i, rule in enumerate(self.rules)])
        return {"area": area, "rules": rules, "levies": copy.deepcopy(self.levies)}

    def user_area(self) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """``(area, rule_sets, levy_sets)`` of ``user_house`` for ``user_grid_fees.json`` (``db_ref`` kept)."""
        entry = self.entry()
        area, rule_sets, levy_sets = user_area_entry(entry, HOUSE_GRID_AREA)
        if "db_ref" in entry["area"]:
            area["db_ref"] = entry["area"]["db_ref"]
        return area, rule_sets, levy_sets

    def document(self, base_document: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """``user_grid_fees.json`` with this area put in (validated); stale own sets of ``user_house`` removed."""
        start = copy.deepcopy(dict(base_document)) if base_document else {"tariff_format": 1, "rule_sets": {}, "areas": []}
        for key, own in (("rule_sets", HOUSE_GRID_AREA), ("levy_sets", f"{HOUSE_GRID_AREA}_levies")):
            sets = start.get(key)
            if isinstance(sets, dict):
                sets.pop(own, None)
        area, rule_sets, levy_sets = self.user_area()
        return put_user_grid_area(start, area, rule_sets=rule_sets, levy_sets=levy_sets)

    def resolve(self, house: HouseSettings) -> GridFee:
        """The grid fee these values give for ``house`` (preview before saving)."""
        document = parse_grid_fee_catalog(self.document(), USER)
        config = parse_grid_fee_config({
            "area_id": HOUSE_GRID_AREA, "power_metering": house.power_metering,
            "quarter_hour_meter": "quarter_hour_meter" in house.capabilities,
        })  # fmt: skip
        return resolve_grid_fee(config, document)


def _unique(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    for part in parts:
        base, number = part["id"], 2
        while part["id"] in seen:
            part["id"], number = f"{base}_{number}", number + 1
        seen.add(part["id"])
    return parts


def load_grid_draft(user_grid_file: Path) -> GridDraft:
    """The own area from ``user_grid_fees.json``, or empty own values when there is none yet."""
    if not user_grid_file.exists():
        return GridDraft()
    document = json.loads(user_grid_file.read_text(encoding="utf-8"))
    parse_grid_fee_catalog(document, USER, str(user_grid_file))
    if not any(isinstance(item, dict) and item.get("id") == HOUSE_GRID_AREA for item in document.get("areas") or []):
        return GridDraft()
    return GridDraft.from_entry(area_document(document, HOUSE_GRID_AREA))
