"""``python -m edibert exchange``: load the catalog package, list templates, query status and report use.

The tariffs in use are the ones ``publish.json`` names; a host such as Earnie collects its own and calls
:mod:`edibert.exchange` directly.
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from edibert.editor.catalog import catalog_package, read_catalog
from edibert.editor.userstore import SECTIONS, read_document
from edibert.errors import EdibertError, ErrorCode
from edibert.exchange import (
    ExchangeClient,
    exchange_config_from_env,
    install_secret,
    plan_usage_reports,
    used_ref,
)
from edibert.i18n import Translator
from edibert.publish.config import CONFIG_NAME, TariffRef, load_publish_config
from edibert.tariff import DbRef
from edibert.trust import trust_level


def _client() -> ExchangeClient:
    config = exchange_config_from_env()
    if config is None:
        raise EdibertError(ErrorCode.EXCHANGE_OFF, "The exchange is switched off (EDIBERT_EXCHANGE_OFF=1).", env="EDIBERT_EXCHANGE_OFF")
    return ExchangeClient(config)


def used_refs(data_dir: Path, catalog: Path | None, config_path: Path | None) -> list[DbRef]:
    """Database versions of the tariffs ``publish.json`` names (a tariff standing for none is left out)."""
    refs = load_publish_config(config_path or data_dir / CONFIG_NAME).tariffs
    return list(used_ref_map(data_dir, catalog, refs).values())


def used_ref_map(data_dir: Path, catalog: Path | None, refs: Sequence[TariffRef]) -> dict[TariffRef, DbRef]:
    """The database version each of ``refs`` stands for; a tariff standing for none has no entry."""
    user = read_document(data_dir / "user_tariffs.json")
    raws: dict[tuple[str, str], Any] = {(d, raw.get("id")): raw for d, section in SECTIONS.items() for raw in user.get(section, [])}
    from_package = False
    if catalog is not None:
        from_package = catalog_package(catalog) is not None
        raws |= {(entry.direction, entry.raw.get("id")): entry.raw for entry in read_catalog(catalog)}
    result = {}
    for ref in refs:
        raw = raws.get((ref.direction, ref.id))
        if raw is None:
            raise EdibertError(ErrorCode.TARIFF_NOT_FOUND, f"Tariff '{ref.id}' ({ref.direction}) is not in the user file or catalog.",
                               tariff_id=ref.id, direction=ref.direction)  # fmt: skip
        found = used_ref(raw, ref.direction, from_package)
        if found is not None:
            result[ref] = found
    return result


def _known_package_id(catalog: Path | None) -> str | None:
    if catalog is None or not catalog.exists():
        return None
    package = json.loads(catalog.read_text(encoding="utf-8")).get("package")
    return package.get("package_id") if isinstance(package, dict) else None


def run_exchange(args: argparse.Namespace, t: Translator, sleep: Callable[[float], None] = time.sleep) -> list[str]:
    client = _client()
    if args.exchange_command == "fetch":
        document = client.fetch_package(_known_package_id(args.catalog))
        if document is None:
            return [t.t("cli.exchange_unchanged")]
        args.out.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        return [t.t("cli.exchange_fetched", path=str(args.out))]
    if args.exchange_command == "templates":
        return _templates(args, t, client)
    refs = used_refs(args.data_dir, args.catalog, args.config)
    if not refs:
        return [t.t("cli.exchange_nothing")]
    if args.exchange_command == "status":
        lines = []
        for entry in client.query_status([(ref.id, ref.version) for ref in refs]):
            if not entry.known:
                lines.append(t.t("cli.exchange_status_unknown", db_id=entry.db_id))
                continue
            key = "cli.exchange_status_outdated" if entry.outdated else "cli.exchange_status"
            lines.append(t.t(key, db_id=entry.db_id, count=entry.installations_12m,
                             trust=t.t(f"trust.{trust_level(entry.check_state, entry.reliable)}"),
                             reliable=t.t("cli.exchange_reliable_yes" if entry.reliable else "cli.exchange_reliable_no"),
                             valid_from=entry.latest_valid_from.isoformat() if entry.latest_valid_from else "-"))  # fmt: skip
            if entry.checked_available:
                lines.append(t.t("cli.exchange_status_checked_available", db_id=entry.db_id, version=str(entry.latest_checked_version)[:12]))
            if entry.merged_into is not None:
                lines.append(t.t("cli.exchange_status_merged", db_id=entry.db_id, target=entry.merged_into.id))
        return lines
    start = datetime.now(UTC)
    reports = plan_usage_reports(refs, install_secret(args.data_dir), start)
    for report in reports:
        if not args.no_delay:
            sleep(max(0.0, (report.send_at - datetime.now(UTC)).total_seconds()))
        client.report_usage(report.db_id, report.version, report.pseudonym)
    return [t.t("cli.exchange_reported", count=len(reports))]


def _templates(args: argparse.Namespace, t: Translator, client: ExchangeClient) -> list[str]:
    """Route 5 as a list (or JSON). Templates are unchecked: copy one in the editor, never import it as catalog."""
    found = client.list_templates(args.land, args.direction, args.grid_area, args.supplier)
    if args.format == "json":
        items = [{"db_id": item.db_id, "version": item.version, "direction": item.direction, "tariff": dict(item.tariff),
                  "valid_from": item.valid_from.isoformat() if item.valid_from else None, "check_state": item.check_state,
                  "reliable": item.reliable, "installations_12m": item.installations_12m,
                  "latest_version": item.latest_version, "latest_checked_version": item.latest_checked_version}
                 for item in found.templates]  # fmt: skip
        return [json.dumps({"templates": items, "truncated": found.truncated}, ensure_ascii=False, indent=2)]
    if not found.templates:
        return [t.t("cli.exchange_templates_none")]
    lines = [t.t("cli.exchange_templates_note")]
    for item in found.templates:
        lines.append(t.t("cli.exchange_template", db_id=item.db_id, version=item.version[:12],
                         label=str(item.tariff.get("label", "")), supplier=str(item.tariff.get("supplier_id", "")),
                         trust=t.t(f"trust.{trust_level(item.check_state, item.reliable)}"),
                         count=item.installations_12m))  # fmt: skip
    if found.truncated:
        lines.append(t.t("cli.exchange_templates_truncated", count=len(found.templates)))
    return lines
