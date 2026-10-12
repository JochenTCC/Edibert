"""``python -m edbert publish``: the command behind the MQTT publisher."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

from edbert.i18n import Translator
from edbert.publish.mqtt import PrintLink, connect
from edbert.publish.service import build_publisher


def run_publish(args: argparse.Namespace, t: Translator) -> int:
    """Publish once (``--once``) or keep publishing every quarter-hour. Returns the exit code."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    link_factory = (lambda _settings: PrintLink()) if args.dry_run else connect
    publisher = build_publisher(args.data_dir, catalog=args.catalog, config_path=args.config, link_factory=link_factory)
    broker = publisher.config.mqtt
    print(t.t("cli.publish_start", count=len(publisher.items), host=broker.host, port=broker.port))
    if args.dry_run:
        print(t.t("cli.publish_dry_run"))
    if not args.once:
        publisher.run_forever()
        return 0
    publisher.announce()
    now = datetime.now(UTC)
    report = publisher.run_cycle(now)
    publisher.link.close()
    print(t.t("cli.publish_cycle", time=now.astimezone(publisher.tz).strftime("%H:%M"), published=", ".join(report.published) or "-"))
    if report.offline:
        print(t.t("cli.publish_offline", offline=", ".join(name for name, _ in report.offline)), file=sys.stderr)
        for _, err in report.offline:
            print(t.error(err), file=sys.stderr)
    for note in report.notes:
        print(t.warning(note), file=sys.stderr)
    return 1 if report.offline else 0
