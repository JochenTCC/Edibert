"""Sharing user tariffs with the free catalog (backlog ``0.1.d`` Catalog P6): payload, selection, transport.

The payload is built from a **whitelist**: prices, type, rules, fees, VAT, land, supplier and product, the
origin of the price sheet and the validity. Everything else (the local ID, notes, ``behavior_notes``,
``$comment``, rule labels, any future field) is dropped, never copied. A tariff marked ``individual`` is
always refused (``CONTRIBUTION_INDIVIDUAL``).

Nothing here talks to a server. The transport is a replaceable adapter (:class:`ContributionTransport`);
without a configured one sharing is off and says so (``CONTRIBUTION_TRANSPORT_OFF``). The exchange with the
server (route, answer, ``db_ref``) is Catalog P7; identity and version hash (Catalog P1) are attached to the
envelope there, see :func:`contribution_payload`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from edibert.editor.userstore import SECTIONS
from edibert.errors import EdibertError, ErrorCode
from edibert.tariff import EXPORT, FEE_FIELDS, IMPORT, DbRef, parse_tariff

CONTRIBUTION_FORMAT = 1

# Top-level tariff fields that go into the payload. ``area_id``, ``valid_from`` and ``valid_to`` are not
# tariff fields yet (grid-fee contributions, validity versions of Catalog P2); a tariff carrying them fails
# ``parse_tariff`` today, so they appear in a payload only once the format allows them.
TARIFF_WHITELIST = (
    "type", "label", "supplier_id", "land", "regions", "currency",
    "fix_cent_kwh", "k_push_cent", "monthly_rates", "settlement_fee_cent_kwh", "markup_percent",
    "feed_in_fee_factor", "feed_in_fix_cent", "settlement_mtu", "prices_include_vat", "vat_percent",
    "rules", "price_floor_cent_kwh", "price_cap_cent_kwh", "requires", "holidays", "extra_holiday_dates",
    *FEE_FIELDS,
    "area_id", "source", "last_verified", "valid_from", "valid_to",
)  # fmt: skip
# Rule fields that go into the payload: everything that changes a price, not the free-text ``label``.
RULE_WHITELIST = ("id", "valid_from", "valid_to", "months", "weekdays", "time", "effect", "when_market_cent_kwh", "requires")
_NESTED_WHITELIST = {
    "monthly_rates": ("year", "month", "tariff_cent_kwh"),
    "holidays": ("treat_as",),
    "time": ("from", "to"),
    "effect": ("mode", "value"),
    "when_market_cent_kwh": ("below", "above"),
}


class ShareDefault(StrEnum):
    """Whether a user tariff is selected for sharing before the user decides (set by the embedding program)."""

    SHARE = "share"  # stand-alone Edibert: shared unless the user leaves it out
    OPT_IN = "opt_in"  # Earnie: shared only after the user selects it


def check_share_default(value: object) -> ShareDefault:
    """The embedding program must say how sharing starts; there is no implicit default."""
    if not isinstance(value, ShareDefault):
        raise TypeError(f"share_default must be a ShareDefault ({', '.join(s.value for s in ShareDefault)}), got {value!r}.")
    return value


def _pick(raw: Mapping[str, Any], allowed: Sequence[str]) -> dict[str, Any]:
    return {key: raw[key] for key in allowed if key in raw}


def _rule(raw: Mapping[str, Any]) -> dict[str, Any]:
    rule = _pick(raw, RULE_WHITELIST)
    for key in ("time", "effect", "when_market_cent_kwh"):
        if isinstance(rule.get(key), Mapping):
            rule[key] = _pick(rule[key], _NESTED_WHITELIST[key])
    return rule


def _tariff_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    tariff = _pick(raw, TARIFF_WHITELIST)
    if "rules" in tariff:
        tariff["rules"] = [_rule(rule) for rule in tariff["rules"]]
    if "monthly_rates" in tariff:
        tariff["monthly_rates"] = [_pick(row, _NESTED_WHITELIST["monthly_rates"]) for row in tariff["monthly_rates"]]
    if "holidays" in tariff:
        tariff["holidays"] = _pick(tariff["holidays"], _NESTED_WHITELIST["holidays"])
    return tariff


def contribution_payload(raw: Mapping[str, Any], direction: str) -> dict[str, Any]:
    """The payload for one user tariff (the stored object of ``user_tariffs.json``).

    The tariff is checked like any tariff first (``parse_tariff``: an invalid tariff is never shared), then
    copied field by field from the whitelist. ``individual: true`` is ``CONTRIBUTION_INDIVIDUAL``.
    Catalog P1/P7 add ``identity`` and ``version`` to this envelope; nothing else goes in.
    """
    tariff = parse_tariff(raw, direction)
    if tariff.individual:
        raise EdibertError(
            ErrorCode.CONTRIBUTION_INDIVIDUAL,
            f"Tariff '{tariff.id}' is marked individual and is never shared.",
            tariff_id=tariff.id,
        )
    return {"contribution_format": CONTRIBUTION_FORMAT, "direction": direction, "tariff": _tariff_fields(raw)}


def payload_text(payload: Mapping[str, Any]) -> str:
    """The exact text of a payload: shown in the preview and sent by a transport, byte for byte."""
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


@dataclass(frozen=True)
class ContributionItem:
    """One user tariff in the share list: its payload, or the coded reason it cannot be shared."""

    direction: str
    tariff_id: str
    label: str
    payload: dict[str, Any] | None
    error: EdibertError | None

    @property
    def shareable(self) -> bool:
        return self.payload is not None


def contribution_items(document: Mapping[str, Any]) -> list[ContributionItem]:
    """Every tariff of a user document (``read_document``), imports first, each with payload or error."""
    items = []
    for direction in (IMPORT, EXPORT):
        for raw in document.get(SECTIONS[direction], []):
            tariff_id = str(raw.get("id", "?"))
            label = str(raw.get("label") or tariff_id)
            try:
                items.append(ContributionItem(direction, tariff_id, label, contribution_payload(raw, direction), None))
            except EdibertError as err:
                items.append(ContributionItem(direction, tariff_id, label, None, err))
    return items


def initially_selected(item: ContributionItem, share_default: ShareDefault) -> bool:
    """Start value of the per-tariff choice: never for a tariff that cannot be shared."""
    return item.shareable and check_share_default(share_default) is ShareDefault.SHARE


class SendStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SendResult:
    """Answer of a transport for one payload. ``code`` names the reason of a rejection; ``db_ref`` is the database
    entry an accepted or duplicate tariff now stands for (contract: ``docs/spec/catalog-exchange.md``)."""

    status: SendStatus
    code: str | None = None
    db_ref: DbRef | None = None


@runtime_checkable
class ContributionTransport(Protocol):
    """Sends one payload. An implementation sends ``payload_text(payload)`` unchanged and raises a coded
    ``EdibertError`` when it cannot deliver; it never retries silently with other content."""

    def send(self, payload: Mapping[str, Any]) -> SendResult: ...


def send_selected(transport: ContributionTransport | None, payloads: Sequence[Mapping[str, Any]]) -> list[SendResult]:
    """Send each payload through ``transport``. ``None`` (no endpoint configured) is ``CONTRIBUTION_TRANSPORT_OFF``."""
    if transport is None:
        raise EdibertError(ErrorCode.CONTRIBUTION_TRANSPORT_OFF, "No contribution transport is configured; sharing is off.")
    return [transport.send(payload) for payload in payloads]
