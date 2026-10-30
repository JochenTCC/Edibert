"""Exchange with the tariff database server (backlog ``0.1.d`` Catalog P7); contract: ``docs/spec/catalog-exchange.md``.

Edibert computes locally and offline; the server only delivers packages and counts use, so nothing here is on
the path of a price. Every request goes through :class:`ExchangeClient`; ``EDIBERT_EXCHANGE_OFF=1`` stops all of
them (``EXCHANGE_OFF``), whatever a host configured. No request carries an installation ID: use is reported per
tariff under a pseudonym computed here from a secret that never leaves the data folder.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from random import Random
from typing import Any

from edibert import __version__
from edibert.contribution import SendResult, SendStatus
from edibert.errors import EdibertError, ErrorCode
from edibert.identity import db_ref_for, differs_from_db, tariff_version
from edibert.store import USER_PREFIX
from edibert.tariff import DATABASES, DbRef, parse_tariff

DEFAULT_BASE_URL = "https://cloudserver.earnie-hems.com"
PREFIX = "/edibert/v1"
ENV_URL = "EDIBERT_EXCHANGE_URL"
ENV_OFF = "EDIBERT_EXCHANGE_OFF"
ENV_ACCESS_KEY = "EDIBERT_ACCESS_KEY"
SECRET_FILE = "exchange_secret"
USER_AGENT = f"Edibert/{__version__} (tariff exchange)"
TIMEOUT_S = 20.0
MAX_STATUS_ENTRIES = 100
DB_ID = re.compile(r"^[A-Z]{2}/(import|export|grid)/[a-z0-9_]+$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class HttpAnswer:
    status: int
    headers: Mapping[str, str]
    body: bytes


# (method, url, body or None, headers, timeout) -> answer; raises OSError when the server cannot be reached.
HttpSend = Callable[[str, str, bytes | None, Mapping[str, str], float], HttpAnswer]


def urllib_send(method: str, url: str, body: bytes | None, headers: Mapping[str, str], timeout: float) -> HttpAnswer:
    """Default transport (standard library). An HTTP error status is an answer, not an exception."""
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HttpAnswer(response.status, {k.lower(): v for k, v in response.headers.items()}, response.read())
    except urllib.error.HTTPError as exc:
        return HttpAnswer(exc.code, {k.lower(): v for k, v in exc.headers.items()}, exc.read())


@dataclass(frozen=True)
class ExchangeConfig:
    """Where the server is and the access key for the verified database (``None``: free database only)."""

    base_url: str = DEFAULT_BASE_URL
    access_key: str | None = None
    timeout_s: float = TIMEOUT_S


def exchange_off(env: Mapping[str, str] | None = None) -> bool:
    """The hard off switch: ``EDIBERT_EXCHANGE_OFF=1``."""
    return (os.environ if env is None else env).get(ENV_OFF, "") == "1"


def exchange_config_from_env(env: Mapping[str, str] | None = None) -> ExchangeConfig | None:
    """Stand-alone settings: ``None`` when switched off, else base URL and access key from the environment."""
    environment = os.environ if env is None else env
    if exchange_off(environment):
        return None
    return ExchangeConfig(environment.get(ENV_URL) or DEFAULT_BASE_URL, environment.get(ENV_ACCESS_KEY) or None)


@dataclass(frozen=True)
class SubmitAnswer:
    status: SendStatus
    code: str | None
    db_ref: DbRef | None  # for accepted and duplicate: the reference the local tariff takes over


@dataclass(frozen=True)
class StatusEntry:
    db_id: str
    version: str
    known: bool
    reliable: bool = False
    installations_12m: int = 0
    latest_version: str | None = None
    latest_valid_from: date | None = None

    @property
    def outdated(self) -> bool:
        return self.known and self.latest_version is not None and self.latest_version != self.version


def _answer_invalid(route: str, detail: str) -> EdibertError:
    return EdibertError(ErrorCode.EXCHANGE_ANSWER_INVALID, f"Answer of {route} does not match the contract: {detail}", route=route)


def _check(value: object, pattern: re.Pattern[str], route: str, name: str) -> str:
    if not isinstance(value, str) or not pattern.match(value):
        raise _answer_invalid(route, f"{name}={value!r}")
    return value


class ExchangeClient:
    """The five routes of the contract. ``send`` is injectable (tests, a host's own HTTP stack)."""

    def __init__(self, config: ExchangeConfig, send: HttpSend = urllib_send, env: Mapping[str, str] | None = None) -> None:
        self.config = config
        self._send = send
        self._env = env

    def _request(self, method: str, route: str, body: Mapping[str, Any] | None = None, headers: Mapping[str, str] | None = None) -> HttpAnswer:
        if exchange_off(self._env):
            raise EdibertError(ErrorCode.EXCHANGE_OFF, f"The exchange is switched off ({ENV_OFF}=1).", env=ENV_OFF)
        all_headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
            all_headers["Content-Type"] = "application/json"
        url = self.config.base_url.rstrip("/") + PREFIX + route
        try:
            answer = self._send(method, url, data, all_headers, self.config.timeout_s)
        except OSError as exc:
            raise EdibertError(ErrorCode.EXCHANGE_UNREACHABLE, f"{method} {route}: {exc}", route=route) from exc
        if answer.status < 400:
            return answer
        code = self._server_code(answer)
        if answer.status in (401, 403):
            raise EdibertError(ErrorCode.EXCHANGE_ACCESS_DENIED, f"{method} {route}: {answer.status} {code}", route=route, server_code=code)
        if answer.status == 429:
            retry = answer.headers.get("retry-after", "")
            raise EdibertError(ErrorCode.EXCHANGE_RATE_LIMITED, f"{method} {route}: rate limited", route=route, retry_after=retry)
        if answer.status >= 500:
            raise EdibertError(ErrorCode.EXCHANGE_UNREACHABLE, f"{method} {route}: {answer.status}", route=route)
        raise EdibertError(ErrorCode.EXCHANGE_REJECTED, f"{method} {route}: {answer.status} {code}", route=route, server_code=code)

    @staticmethod
    def _server_code(answer: HttpAnswer) -> str:
        try:
            code = json.loads(answer.body.decode("utf-8")).get("code")
        except (ValueError, AttributeError):
            return str(answer.status)
        return str(code) if code else str(answer.status)

    @staticmethod
    def _json(answer: HttpAnswer, route: str) -> Any:
        try:
            return json.loads(answer.body.decode("utf-8"))
        except ValueError as exc:
            raise _answer_invalid(route, "no JSON body") from exc

    def fetch_package(self, database: str, known_package_id: str | None = None) -> dict[str, Any] | None:
        """Route 1: the latest package file of ``database``; ``None`` when ``known_package_id`` is still the latest.

        The file is returned unchecked; the caller runs ``verify_package`` and the import.
        """
        if database not in DATABASES:
            raise EdibertError(ErrorCode.VALUE_INVALID, f"database={database!r}", field="database", value=database)
        headers = {}
        if database == "verified":
            if not self.config.access_key:
                raise EdibertError(ErrorCode.EXCHANGE_ACCESS_DENIED, "The verified database needs an access key.", route="packages", server_code="ACCESS_KEY_MISSING")
            headers["Authorization"] = f"Bearer {self.config.access_key}"
        if known_package_id:
            headers["If-None-Match"] = f'"{known_package_id}"'
        route = f"/packages/{database}/latest"
        answer = self._request("GET", route, headers=headers)
        if answer.status == 304:
            return None
        document = self._json(answer, route)
        if not isinstance(document, dict):
            raise _answer_invalid(route, "package is not an object")
        return document

    def submit(self, payload: Mapping[str, Any], db_ref: DbRef | None = None) -> SubmitAnswer:
        """Route 2: one P6 payload with its version (and ``based_on`` when the tariff has a ``db_ref``)."""
        body = {**payload, "version": payload_version(payload)}
        if db_ref is not None:
            body["based_on"] = db_ref.to_dict()
        route = "/tariffs"
        data = self._json(self._request("POST", route, body), route)
        if not isinstance(data, dict):
            raise _answer_invalid(route, "answer is not an object")
        try:
            status = SendStatus(data.get("status"))
        except ValueError as exc:
            raise _answer_invalid(route, f"status={data.get('status')!r}") from exc
        if status is SendStatus.REJECTED:
            return SubmitAnswer(status, str(data.get("code") or "?"), None)
        ref = DbRef("free", _check(data.get("db_id"), DB_ID, route, "db_id"), _check(data.get("version"), HEX64, route, "version"))
        return SubmitAnswer(status, None, ref)

    def report_usage(self, db_id: str, version: str, pseudonym: str) -> None:
        """Route 3: one entry, one request (never batched; see :func:`plan_usage_reports`)."""
        self._request("POST", "/usage", {"db_id": db_id, "version": version, "pseudonym": pseudonym})

    def query_status(self, refs: Sequence[tuple[str, str]]) -> list[StatusEntry]:
        """Route 4: status of ``(db_id, version)`` pairs, in the same order (asked in chunks of 100)."""
        result: list[StatusEntry] = []
        for start in range(0, len(refs), MAX_STATUS_ENTRIES):
            chunk = refs[start : start + MAX_STATUS_ENTRIES]
            route = "/status"
            data = self._json(self._request("POST", route, {"entries": [{"db_id": d, "version": v} for d, v in chunk]}), route)
            entries = data.get("entries") if isinstance(data, dict) else None
            if not isinstance(entries, list) or len(entries) != len(chunk):
                raise _answer_invalid(route, "entries do not match the request")
            result.extend(_status_entry(item, route) for item in entries)
        return result


def _status_entry(item: object, route: str) -> StatusEntry:
    if not isinstance(item, dict) or not isinstance(item.get("known"), bool):
        raise _answer_invalid(route, f"entry {item!r}")
    db_id, version = _check(item.get("db_id"), DB_ID, route, "db_id"), _check(item.get("version"), HEX64, route, "version")
    if not item["known"]:
        return StatusEntry(db_id, version, False)
    latest = item.get("latest_version")
    valid_from = item.get("latest_valid_from")
    try:
        return StatusEntry(
            db_id, version, True, bool(item.get("reliable")), int(item.get("installations_12m") or 0),
            None if latest is None else _check(latest, HEX64, route, "latest_version"),
            None if valid_from is None else date.fromisoformat(valid_from),
        )  # fmt: skip
    except (TypeError, ValueError) as exc:
        raise _answer_invalid(route, f"entry {item!r}") from exc


def payload_version(payload: Mapping[str, Any]) -> str:
    """``tariff_version`` of a P6 payload. The payload has no ID; the ID never enters a version."""
    return tariff_version({**payload["tariff"], "id": "shared"}, payload["direction"])


class ServerTransport:
    """The P6 ``ContributionTransport`` that submits to the server (route 2)."""

    def __init__(self, client: ExchangeClient) -> None:
        self.client = client

    def send(self, payload: Mapping[str, Any], db_ref: DbRef | None) -> SendResult:
        answer = self.client.submit(payload, db_ref)
        return SendResult(answer.status, answer.code, answer.db_ref)


# --- report use -----------------------------------------------------------------------------------------------


def install_secret(data_dir: Path) -> bytes:
    """The installation's secret (32 random bytes in ``exchange_secret``), created on first use; never sent."""
    path = data_dir / SECRET_FILE
    if path.exists():
        text = path.read_text(encoding="ascii").strip()
        if not HEX64.match(text):
            raise EdibertError(ErrorCode.FILE_INVALID, f"'{path}' is not a 64-digit hex secret.", path=str(path))
        return bytes.fromhex(text)
    data_dir.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_bytes(32)
    path.write_text(secret.hex(), encoding="ascii")
    return secret


def usage_pseudonym(secret: bytes, db_id: str) -> str:
    """``HMAC-SHA256(secret, db_id)``: stable per tariff, different for every tariff of the installation."""
    return hmac.new(secret, db_id.encode("utf-8"), hashlib.sha256).hexdigest()


def used_ref(raw: Mapping[str, Any], direction: str, catalog_database: str | None) -> DbRef | None:
    """The database version a tariff in use stands for, or ``None`` when it stands for none.

    A user tariff counts with its ``db_ref`` while its prices are unchanged; a catalog tariff counts when its
    catalog came from a package (``catalog_database``). A user tariff with changed prices is a version the
    database does not know and is not reported.
    """
    tariff = parse_tariff(raw, direction)
    if tariff.db_ref is not None:
        return None if differs_from_db(raw, direction) else tariff.db_ref
    if not tariff.id.startswith(USER_PREFIX) and catalog_database is not None:
        return DbRef(**db_ref_for(raw, direction, catalog_database))
    return None


@dataclass(frozen=True)
class UsageReport:
    send_at: datetime
    db_id: str
    version: str
    pseudonym: str


def plan_usage_reports(refs: Sequence[DbRef], secret: bytes, start: datetime, rng: Random | None = None) -> list[UsageReport]:
    """One report per distinct entry, each at its own random time within 24 h from ``start``, sorted by time."""
    random = rng or Random(secrets.randbits(64))
    unique = {(ref.id, ref.version) for ref in refs}
    reports = [
        UsageReport(start + timedelta(seconds=random.uniform(0, 86_400)), db_id, version, usage_pseudonym(secret, db_id))
        for db_id, version in sorted(unique)
    ]
    return sorted(reports, key=lambda report: report.send_at)
