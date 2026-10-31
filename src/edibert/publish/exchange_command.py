"""``python -m edibert exchange``: load a package, query status and report use from the command line.

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

from edibert.editor.catalog import catalog_database, read_catalog
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
    database = None
    if catalog is not None:
        database = catalog_database(catalog)
        raws |= {(entry.direction, entry.raw.get("id")): entry.raw for entry in read_catalog(catalog)}
    result = {}
    for ref in refs:
        raw = raws.get((ref.direction, ref.id))
        if raw is None:
            raise EdibertError(ErrorCode.TARIFF_NOT_FOUND, f"Tariff '{ref.id}' ({ref.direction}) is not in the user file or catalog.",
                               tariff_id=ref.id, direction=ref.direction)  # fmt: skip
        found = used_ref(raw, ref.direction, database)
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
        document = client.fetch_package(args.database, _known_package_id(args.catalog))
        if document is None:
            return [t.t("cli.exchange_unchanged", database=args.database)]
        args.out.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        return [t.t("cli.exchange_fetched", database=args.database, path=str(args.out))]
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
                             reliable=t.t("cli.exchange_reliable_yes" if entry.reliable else "cli.exchange_reliable_no"),
                             valid_from=entry.latest_valid_from.isoformat() if entry.latest_valid_from else "-"))  # fmt: skip
        return lines
    start = datetime.now(UTC)
    reports = plan_usage_reports(refs, install_secret(args.data_dir), start)
    for report in reports:
        if not args.no_delay:
            sleep(max(0.0, (report.send_at - datetime.now(UTC)).total_seconds()))
        client.report_usage(report.db_id, report.version, report.pseudonym)
    return [t.t("cli.exchange_reported", count=len(reports))]
