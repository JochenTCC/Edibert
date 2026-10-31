"""Signed catalog packages (Catalog P4, package format 2): format, signature check and the content checks.

A package is one JSON file::

    {"edibert_package": 2,
     "manifest": {"package_id", "issued_at", "valid_until", "tariff_format", "key_id", "files"},
     "content": {"tariffs.json": {...}, "grid_fees.json": {...}},
     "signature": "<base64 Ed25519 signature over the canonical manifest>"}

The signature covers the manifest; the manifest holds the SHA-256 of every content file. So nothing in the
package can change without breaking the check, and the check needs no network. Edibert only verifies:
the private key lives with the tariff database, never in this repository and never on a server.
There is one tariff database and one catalog: every tariff and every grid area of a package carries its ``check``
(``checked`` or ``released_by_supplier``), because the signature stands for checked versions only. Format 1 (with
``manifest.database``) was never published and is not read.
An expired package (``valid_until`` in the past) stays usable and only warns: a client keeps the last package
received.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from edibert._fields import as_dict, check_known, get_date, get_str, invalid, missing
from edibert.errors import EdibertError, EdibertWarning, ErrorCode, WarningCode
from edibert.fileformat import CATALOG_FILE, GRID_CATALOG_FILE, check_tariff_format
from edibert.gridfee import parse_grid_fee_catalog
from edibert.identity import grid_area_identity, tariff_identity
from edibert.store import parse_tariff_documents
from edibert.tariff import EXPORT, IMPORT

PACKAGE_KEY = "edibert_package"
PACKAGE_FORMAT = 2
SUPPORTED_PACKAGE_FORMATS = (2,)
ROOT_FIELDS = (PACKAGE_KEY, "manifest", "content", "signature")
MANIFEST_FIELDS = ("package_id", "issued_at", "valid_until", "tariff_format", "key_id", "files")
CONTENT_FILES = (CATALOG_FILE, GRID_CATALOG_FILE)
SECTIONS = {IMPORT: "import_tariffs", EXPORT: "export_tariffs"}

# Public keys of the tariff database by key ID (raw Ed25519 key, base64). Several entries allow a key change:
# a new key is added before the first package signed with it, an old one is removed after its last package
# expired. Empty until the first signing key exists; callers can pass their own (tests, a self-hosted base).
TRUSTED_KEYS: Mapping[str, str] = {"edibert-2026-1": "6sbs0jOqfz4ue7lCike6mVkZX2Zs4m+EqXgrgWPaM44="}


@dataclass(frozen=True)
class PackageManifest:
    package_id: str
    issued_at: datetime
    valid_until: date
    tariff_format: int
    key_id: str
    files: Mapping[str, str]  # content file name -> SHA-256 (hex) of its canonical JSON

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            "issued_at": self.issued_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "tariff_format": self.tariff_format,
            "key_id": self.key_id,
            "files": dict(self.files),
        }


@dataclass(frozen=True)
class CatalogPackage:
    """A verified package: manifest, the two catalog documents and non-fatal findings (``PACKAGE_EXPIRED``)."""

    manifest: PackageManifest
    tariffs: Mapping[str, Any]
    grid_fees: Mapping[str, Any]
    warnings: tuple[EdibertWarning, ...] = field(default=())


def canonical_bytes(document: Any) -> bytes:
    """The bytes that are hashed and signed: JSON with sorted keys, no spaces, UTF-8."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_hash(document: Any) -> str:
    return hashlib.sha256(canonical_bytes(document)).hexdigest()


def public_key_text(key: Ed25519PublicKey) -> str:
    """A public key as it is listed in ``TRUSTED_KEYS`` (raw bytes, base64)."""
    return base64.b64encode(key.public_bytes(Encoding.Raw, PublicFormat.Raw)).decode("ascii")


def build_package(
    tariffs: Mapping[str, Any],
    grid_fees: Mapping[str, Any],
    manifest: Mapping[str, Any],
    private_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    """A signed package from the two catalog documents and the manifest fields (without ``files``).

    For the tariff database's signing step and for tests; the result passes :func:`verify_package` with the
    matching public key.
    """
    content = {CATALOG_FILE: dict(tariffs), GRID_CATALOG_FILE: dict(grid_fees)}
    signed = {**manifest, "files": {name: content_hash(doc) for name, doc in content.items()}}
    signature = private_key.sign(canonical_bytes(signed))
    return {
        PACKAGE_KEY: PACKAGE_FORMAT,
        "manifest": signed,
        "content": content,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def read_package(path: Path) -> Mapping[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read package '{path}': {exc}", path=str(path)) from exc
    return as_dict(data, str(path))


def load_trusted_keys(path: Path) -> dict[str, str]:
    """Extra trusted keys from a JSON file ``{"<key_id>": "<base64 public key>"}``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EdibertError(ErrorCode.FILE_INVALID, f"Cannot read key file '{path}': {exc}", path=str(path)) from exc
    keys = as_dict(data, str(path))
    for key_id, text in keys.items():
        _public_key(text, f"{path}.{key_id}")
    return dict(keys)


def _public_key(text: object, path: str) -> Ed25519PublicKey:
    try:
        raw = base64.b64decode(str(text), validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except (binascii.Error, ValueError) as exc:
        raise invalid(path, text) from exc


def _parse_manifest(raw: object) -> PackageManifest:
    data = as_dict(raw, "manifest")
    check_known(data, MANIFEST_FIELDS, "manifest")
    issued_text = get_str(data, "issued_at", "manifest", required=True)
    try:
        issued_at = datetime.fromisoformat(str(issued_text))
    except ValueError as exc:
        raise invalid("manifest.issued_at", issued_text) from exc
    if issued_at.tzinfo is None:
        raise invalid("manifest.issued_at", issued_text)
    valid_until = get_date(data, "valid_until", "manifest")
    if valid_until is None:
        raise missing("manifest.valid_until")
    tariff_format = data.get("tariff_format")
    if tariff_format is None:
        raise missing("manifest.tariff_format")
    if isinstance(tariff_format, bool) or not isinstance(tariff_format, int):
        raise invalid("manifest.tariff_format", tariff_format)
    files = as_dict(data.get("files"), "manifest.files")
    if sorted(files) != sorted(CONTENT_FILES):
        raise invalid("manifest.files", sorted(files))
    return PackageManifest(
        package_id=get_str(data, "package_id", "manifest", required=True) or "",
        issued_at=issued_at,
        valid_until=valid_until,
        tariff_format=tariff_format,
        key_id=get_str(data, "key_id", "manifest", required=True) or "",
        files={name: str(value) for name, value in files.items()},
    )


def _check_signature(document: Mapping[str, Any], manifest: PackageManifest, keys: Mapping[str, str]) -> None:
    if manifest.key_id not in keys:
        raise EdibertError(
            ErrorCode.PACKAGE_KEY_UNKNOWN, f"Package key '{manifest.key_id}' is not trusted.", key_id=manifest.key_id
        )
    key = _public_key(keys[manifest.key_id], f"trusted_keys.{manifest.key_id}")
    try:
        signature = base64.b64decode(str(document.get("signature", "")), validate=True)
        key.verify(signature, canonical_bytes(document["manifest"]))
    except (binascii.Error, InvalidSignature) as exc:
        raise EdibertError(
            ErrorCode.PACKAGE_SIGNATURE_INVALID,
            f"The signature of the package does not match key '{manifest.key_id}'.",
            key_id=manifest.key_id,
        ) from exc


def _check_content(content: Mapping[str, Any], manifest: PackageManifest) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if sorted(content) != sorted(CONTENT_FILES):
        raise invalid("content", sorted(content))
    for name in CONTENT_FILES:
        if content_hash(content[name]) != manifest.files[name]:
            raise EdibertError(
                ErrorCode.PACKAGE_CONTENT_MISMATCH, f"Package file '{name}' does not match its hash.", file=name
            )
    tariffs = as_dict(content[CATALOG_FILE], CATALOG_FILE)
    grid_fees = as_dict(content[GRID_CATALOG_FILE], GRID_CATALOG_FILE)
    for name, document in ((CATALOG_FILE, tariffs), (GRID_CATALOG_FILE, grid_fees)):
        if check_tariff_format(document, name) != manifest.tariff_format:
            raise invalid(f"{name}.tariff_format", document.get("tariff_format"))
    parse_tariff_documents(tariffs, None, (CATALOG_FILE, "-"))
    parse_grid_fee_catalog(grid_fees, where=GRID_CATALOG_FILE)
    for direction, section in SECTIONS.items():  # every database entry needs its identity and its check
        for raw in tariffs.get(section) or []:
            tariff_identity(raw, direction)
            if raw.get("check") is None:
                tariff_id = str(raw.get("id"))
                raise EdibertError(
                    ErrorCode.PACKAGE_ENTRY_UNCHECKED,
                    f"Package tariff '{tariff_id}' has no check; a signed package carries checked versions only.",
                    tariff_id=tariff_id,
                )
    for area in grid_fees.get("areas") or []:  # grid areas too (0.1.d2): checked or operator-released only
        grid_area_identity(area)
        if area.get("check") is None:
            area_id = str(area.get("id"))
            raise EdibertError(
                ErrorCode.PACKAGE_ENTRY_UNCHECKED,
                f"Package grid area '{area_id}' has no check; a signed package carries checked versions only.",
                tariff_id=area_id,
            )
    return tariffs, grid_fees


def verify_package(
    document: Mapping[str, Any],
    *,
    trusted_keys: Mapping[str, str] | None = None,
    today: date | None = None,
) -> CatalogPackage:
    """Check a package offline: format, manifest, signature, content hashes, then the catalogs themselves.

    The signature is checked before the content is read. ``trusted_keys`` replaces :data:`TRUSTED_KEYS`;
    ``today`` (default: the local date) decides ``PACKAGE_EXPIRED``, which is a warning only.
    """
    data = as_dict(document, "package")
    value = data.get(PACKAGE_KEY)
    if isinstance(value, bool) or value not in SUPPORTED_PACKAGE_FORMATS:
        raise EdibertError(
            ErrorCode.PACKAGE_FORMAT_UNSUPPORTED, f"Unsupported package format {value!r}.", value=value
        )
    check_known(data, ROOT_FIELDS, "package")
    manifest = _parse_manifest(data.get("manifest"))
    _check_signature(data, manifest, TRUSTED_KEYS if trusted_keys is None else trusted_keys)
    tariffs, grid_fees = _check_content(as_dict(data.get("content"), "content"), manifest)
    warnings: tuple[EdibertWarning, ...] = ()
    if manifest.valid_until < (today or date.today()):
        until = manifest.valid_until.isoformat()
        warnings = (
            EdibertWarning(
                WarningCode.PACKAGE_EXPIRED,
                f"The catalog package was valid until {until}; it is used without updates.",
                {"valid_until": until},
            ),
        )
    return CatalogPackage(manifest, tariffs, grid_fees, warnings)
