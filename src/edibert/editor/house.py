"""House settings of the editor: time zone, location, capabilities and an optional grid fee."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from edibert.context import PricingContext
from edibert.editor.model import RuleDraft, unique_rule_ids
from edibert.errors import EdibertError, ErrorCode
from edibert.gridfee import GridFee, parse_grid_fee_config, resolve_grid_fee
from edibert.rules import REQUIRES

LANDS = ("AT", "DE", "CH")
DEFAULT_TIMEZONE = "Europe/Vienna"
COMMON_TIMEZONES = (DEFAULT_TIMEZONE, "Europe/Berlin", "Europe/Zurich")


@dataclass
class HouseSettings:
    """Where the house is and what it has. Saved next to the user tariffs as ``house.json``."""

    timezone: str = DEFAULT_TIMEZONE
    land: str = "AT"
    region: str = ""
    capabilities: list[str] = field(default_factory=list)
    grid_enabled: bool = False
    grid_base_cent: float = 0.0
    grid_rules: list[RuleDraft] = field(default_factory=list)

    def context(self) -> PricingContext:
        return PricingContext(self.timezone, self.land or None, self.region or None)

    def grid_config_raw(self) -> dict[str, Any]:
        raw: dict[str, Any] = {
            "base_cent_kwh": self.grid_base_cent,
            "quarter_hour_meter": "quarter_hour_meter" in self.capabilities,
        }
        if self.grid_rules:
            raw["rules"] = unique_rule_ids([rule.to_raw(f"grid_rule_{index + 1}") for index, rule in enumerate(self.grid_rules)])
        return raw

    def grid_fee(self) -> GridFee | None:
        """The resolved grid fee, or ``None`` when it is switched off."""
        if not self.grid_enabled:
            return None
        return resolve_grid_fee(parse_grid_fee_config(self.grid_config_raw()))

    def to_json(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone,
            "land": self.land,
            "region": self.region,
            "capabilities": list(self.capabilities),
            "grid_enabled": self.grid_enabled,
            "grid_base_cent": self.grid_base_cent,
            "grid_rules": [rule.to_raw(f"grid_rule_{index + 1}") for index, rule in enumerate(self.grid_rules)],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> HouseSettings:
        capabilities = [item for item in data.get("capabilities", []) if item in REQUIRES]
        return cls(
            timezone=str(data.get("timezone", DEFAULT_TIMEZONE)),
            land=str(data.get("land", "AT")),
            region=str(data.get("region", "")),
            capabilities=capabilities,
            grid_enabled=bool(data.get("grid_enabled", False)),
            grid_base_cent=float(data.get("grid_base_cent", 0.0)),
            grid_rules=[RuleDraft.from_raw(item) for item in data.get("grid_rules", [])],
        )


def load_house(path: Path) -> HouseSettings:
    """Saved settings, or defaults if there is no file. A broken file is an error."""
    if not path.exists():
        return HouseSettings()
    try:
        return HouseSettings.from_json(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read '{path}': {exc}", path=str(path)) from exc


def save_house(path: Path, house: HouseSettings) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(house.to_json(), stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
