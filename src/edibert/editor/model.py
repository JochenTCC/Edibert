"""Editable form model of a tariff (no UI). It turns form values into the tariff JSON and back."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from edibert._fields import missing as missing_field
from edibert.errors import EdibertError
from edibert.rules import MODE_ABSOLUTE
from edibert.store import USER_PREFIX
from edibert.tariff import EXPORT, IMPORT, Tariff, parse_tariff

KINDS = ("fixed", "spot", "monthly")
TYPE_BY_KIND = {
    IMPORT: {"fixed": "fixed_cent", "spot": "spot_hourly", "monthly": "monthly_table"},
    EXPORT: {"fixed": "fixed", "spot": "spot_hourly", "monthly": "monthly_table"},
}
DAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
HOLIDAY = "holiday"
FEE_KEYS = ("monthly_fee_eur", "metering_monthly_fee_eur", "grid_monthly_fee_eur", "other_monthly_fee_eur")
_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue"}


def slugify(text: str) -> str:
    """ASCII identifier fragment: lower case, letters/digits/underscore."""
    for char, repl in _UMLAUTS.items():
        text = text.replace(char, repl)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "tariff"


def unique_rule_ids(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rule IDs derived from labels can clash (two rows named alike); later ones get ``_2``, ``_3``."""
    seen: set[str] = set()
    for rule in rules:
        base, number = rule["id"], 2
        while rule["id"] in seen:
            rule["id"], number = f"{base}_{number}", number + 1
        seen.add(rule["id"])
    return rules


def _days_from_raw(raw: object) -> list[str]:
    """Weekday filter as an ordered list of day names (plus ``holiday``); empty = every day."""
    if raw is None:
        return []
    items = [raw] if isinstance(raw, str) else list(raw)  # type: ignore[call-overload]
    names: set[str] = set()
    for item in items:
        if isinstance(item, int):
            names.add(DAY_NAMES[item])
        elif item == "weekday":
            names.update(DAY_NAMES[:5])
        elif item == "weekend":
            names.update(DAY_NAMES[5:])
        else:
            names.add(str(item).lower())
    return [name for name in (*DAY_NAMES, HOLIDAY) if name in names]


def _days_to_raw(days: list[str]) -> Any:
    selected = [d for d in (*DAY_NAMES, HOLIDAY) if d in days]
    if not selected or selected == list(DAY_NAMES):
        return None
    if selected == list(DAY_NAMES[:5]):
        return "weekday"
    if selected == list(DAY_NAMES[5:]):
        return "weekend"
    return selected


@dataclass
class RuleDraft:
    """One time window with its effect, as edited in the form."""

    id: str = ""
    label: str = ""
    start: str | None = None  # "HH:MM"; both None = all day
    end: str | None = None
    days: list[str] = field(default_factory=list)
    months: list[int] = field(default_factory=list)
    mode: str = MODE_ABSOLUTE
    value: float = 0.0
    valid_from: str | None = None
    valid_to: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)  # fields the form does not edit (kept as they are)
    uid: int = field(default=0, compare=False, repr=False)  # stable key for form widgets, never stored

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any]) -> RuleDraft:
        known = {"id", "label", "time", "weekdays", "months", "effect", "valid_from", "valid_to"}
        time = raw.get("time") or {}
        effect = raw.get("effect") or {}
        return cls(
            id=str(raw.get("id", "")),
            label=str(raw.get("label", "")),
            start=time.get("from"),
            end=time.get("to"),
            days=_days_from_raw(raw.get("weekdays")),
            months=sorted(raw.get("months") or []),
            mode=str(effect.get("mode", MODE_ABSOLUTE)),
            value=float(effect.get("value") or 0.0),
            valid_from=raw.get("valid_from"),
            valid_to=raw.get("valid_to"),
            extra={key: value for key, value in raw.items() if key not in known},
        )

    def to_raw(self, fallback_id: str) -> dict[str, Any]:
        raw: dict[str, Any] = {"id": self.id or slugify(self.label) or fallback_id}
        if self.label:
            raw["label"] = self.label
        if self.start and self.end:
            raw["time"] = {"from": self.start, "to": self.end}
        if self.months and len(set(self.months)) < 12:
            raw["months"] = sorted(set(self.months))
        days = _days_to_raw(self.days)
        if days is not None:
            raw["weekdays"] = days
        for key, value in (("valid_from", self.valid_from), ("valid_to", self.valid_to)):
            if value:
                raw[key] = value
        raw["effect"] = {"mode": self.mode, "value": self.value}
        raw.update(self.extra)
        return raw


@dataclass
class TariffDraft:
    """Everything the form edits for one tariff. ``extra`` keeps unknown fields untouched."""

    direction: str = IMPORT
    label: str = ""
    supplier: str = ""
    kind: str = "fixed"
    price_cent: float = 0.0  # fix_cent_kwh (import) or k_push_cent (export)
    markup_percent: float = 0.0
    fee_cent: float = 0.0  # settlement_fee_cent_kwh
    feed_in_fee_factor: float = 0.0
    feed_in_fix_cent: float = 0.0
    monthly_rates: list[tuple[int | None, int | None, float | None]] = field(default_factory=list)  # None: empty cell
    settlement_mtu: str = "15min"
    prices_include_vat: bool = True
    vat_percent: float = 0.0
    fees: dict[str, float] = field(default_factory=dict)
    rules: list[RuleDraft] = field(default_factory=list)
    price_floor_cent_kwh: float | None = None
    price_cap_cent_kwh: float | None = None
    requires: list[str] = field(default_factory=list)
    holiday_mode: str = "sunday"
    extra_holiday_dates: list[str] = field(default_factory=list)
    individual: bool = False
    source: str = ""
    last_verified: str | None = None
    behavior_notes: str = ""
    land: str | None = None
    currency: str | None = None
    id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Mapping[str, Any], direction: str) -> TariffDraft:
        kind_by_type = {value: key for key, value in TYPE_BY_KIND[direction].items()}
        known = {
            "id", "label", "type", "supplier_id", "land", "currency", "fix_cent_kwh", "k_push_cent",
            "markup_percent", "settlement_fee_cent_kwh", "feed_in_fee_factor", "feed_in_fix_cent",
            "monthly_rates", "settlement_mtu", "prices_include_vat", "vat_percent", "rules",
            "price_floor_cent_kwh", "price_cap_cent_kwh", "requires", "holidays", "extra_holiday_dates",
            "individual", "source", "last_verified", "behavior_notes", "$comment", *FEE_KEYS,
        }  # fmt: skip
        price = raw.get("fix_cent_kwh") if direction == IMPORT else raw.get("k_push_cent")
        rates = [(r["year"], r["month"], r["tariff_cent_kwh"]) for r in raw.get("monthly_rates") or []]
        return cls(
            direction=direction,
            label=str(raw.get("label", "")),
            supplier=str(raw.get("supplier_id", "")).removeprefix(USER_PREFIX),
            kind=kind_by_type.get(str(raw.get("type")), "fixed"),
            price_cent=float(price or 0.0),
            markup_percent=float(raw.get("markup_percent") or 0.0),
            fee_cent=float(raw.get("settlement_fee_cent_kwh") or 0.0),
            feed_in_fee_factor=float(raw.get("feed_in_fee_factor") or 0.0),
            feed_in_fix_cent=float(raw.get("feed_in_fix_cent") or 0.0),
            monthly_rates=rates,
            settlement_mtu=str(raw.get("settlement_mtu", "15min")),
            prices_include_vat=bool(raw.get("prices_include_vat", True)),
            vat_percent=float(raw.get("vat_percent") or 0.0),
            fees={key: float(raw[key]) for key in FEE_KEYS if key in raw},
            rules=[RuleDraft.from_raw(item) for item in raw.get("rules") or []],
            price_floor_cent_kwh=raw.get("price_floor_cent_kwh"),
            price_cap_cent_kwh=raw.get("price_cap_cent_kwh"),
            requires=list(raw.get("requires") or []),
            holiday_mode=(raw.get("holidays") or {}).get("treat_as", "sunday"),
            extra_holiday_dates=list(raw.get("extra_holiday_dates") or []),
            individual=bool(raw.get("individual", False)),
            source=str(raw.get("source", "")),
            last_verified=raw.get("last_verified"),
            behavior_notes=str(raw.get("behavior_notes", "")),
            land=raw.get("land"),
            currency=raw.get("currency"),
            id=raw.get("id"),
            extra={key: value for key, value in raw.items() if key not in known},
        )

    def tariff_id(self, taken: set[str]) -> str:
        """The stored ID, or a new ``user_`` ID from the label that is not in ``taken``."""
        if self.id:
            return self.id
        base = USER_PREFIX + slugify(self.label)
        candidate, number = base, 2
        while candidate in taken:
            candidate, number = f"{base}_{number}", number + 1
        return candidate

    def _price_fields(self) -> dict[str, Any]:
        if self.kind == "monthly":
            return {"monthly_rates": [{"year": y, "month": m, "tariff_cent_kwh": c} for y, m, c in self.monthly_rates]}
        if self.kind == "fixed":
            return {("fix_cent_kwh" if self.direction == IMPORT else "k_push_cent"): self.price_cent}
        raw: dict[str, Any] = {"settlement_mtu": self.settlement_mtu}
        if self.fee_cent:
            raw["settlement_fee_cent_kwh"] = self.fee_cent
        if self.direction == IMPORT and self.markup_percent:
            raw["markup_percent"] = self.markup_percent
        if self.direction == EXPORT:
            for key, value in (("feed_in_fee_factor", self.feed_in_fee_factor), ("feed_in_fix_cent", self.feed_in_fix_cent)):
                if value:
                    raw[key] = value
        return raw

    def to_raw(self, taken: set[str] | None = None) -> dict[str, Any]:
        """The tariff entry as JSON-ready dict (only fields that carry information)."""
        raw: dict[str, Any] = {"id": self.tariff_id(taken or set())}
        if self.label:
            raw["label"] = self.label
        raw["type"] = TYPE_BY_KIND[self.direction][self.kind]
        raw["supplier_id"] = USER_PREFIX + slugify(self.supplier or self.label)
        for key, value in (("land", self.land), ("currency", self.currency)):
            if value:
                raw[key] = value
        raw.update(self._price_fields())
        raw["prices_include_vat"] = self.prices_include_vat
        raw["vat_percent"] = self.vat_percent
        raw.update(self.fees)
        if self.rules:
            raw["rules"] = unique_rule_ids([rule.to_raw(f"rule_{index + 1}") for index, rule in enumerate(self.rules)])
        self._add_advanced(raw)
        raw.update(self.extra)
        return raw

    def _add_advanced(self, raw: dict[str, Any]) -> None:
        for key, value in (("price_floor_cent_kwh", self.price_floor_cent_kwh), ("price_cap_cent_kwh", self.price_cap_cent_kwh)):
            if value is not None:
                raw[key] = value
        if self.requires:
            raw["requires"] = list(self.requires)
        if self.holiday_mode != "sunday":
            raw["holidays"] = {"treat_as": self.holiday_mode}
        if self.extra_holiday_dates:
            raw["extra_holiday_dates"] = list(self.extra_holiday_dates)
        if self.individual:
            raw["individual"] = True
        for key, value in (("source", self.source), ("last_verified", self.last_verified), ("behavior_notes", self.behavior_notes)):
            if value:
                raw[key] = value


@dataclass(frozen=True)
class Validation:
    """Result of checking a draft with the real parser."""

    raw: dict[str, Any]
    tariff: Tariff | None
    error: EdibertError | None

    @property
    def ok(self) -> bool:
        return self.tariff is not None


def validate(draft: TariffDraft, taken: set[str] | None = None) -> Validation:
    """Build the tariff JSON and parse it strictly; the first problem is returned as coded error."""
    raw = draft.to_raw(taken)
    if not draft.label.strip():
        return Validation(raw, None, missing_field("label"))
    try:
        return Validation(raw, parse_tariff(raw, draft.direction), None)
    except EdibertError as err:
        return Validation(raw, None, err)
