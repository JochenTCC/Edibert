# Catalog exchange with the tariff database server (0.1.d Catalog P7)

Technical contract between the Edibert client (`src/edibert/exchange.py`) and the tariff database server.
The server is not part of this repository; this file is the contract both sides build against. Package
format and import: [tariff-format.md](tariff-format.md) section 11. Payload of a shared tariff: `edibert.contribution`.

## Principles

* **Edibert computes locally and offline.** The server only delivers packages and counts use. An outage, a
  slow answer or a wrong answer never changes a price; every exchange runs beside the calculation.
* **Hard off switch:** `EDIBERT_EXCHANGE_OFF=1` stops every request, whatever a host configured
  (`EXCHANGE_OFF`). A host (Earnie) builds its own `ExchangeConfig` and asks for its own consent.
* **No installation ID**, on any route. Edibert never sends one; a host must not add one.
* **No IP log** on the routes `usage` and `status`: the server and its reverse proxy keep no client address
  for them (no access log line with IP, no rate-limit table kept longer than the limit window).
* Package signatures are checked offline (Catalog P4). The server only holds signed files; the signing key
  never lives on it.

## Common rules

| Item | Value |
|---|---|
| Base URL | `https://cloudserver.earnie-hems.com` (`DEFAULT_BASE_URL`); `EDIBERT_EXCHANGE_URL` overrides it |
| Prefix | `/edibert/v1` |
| Request body | JSON, UTF-8, `Content-Type: application/json`, at most 64 KiB (`413` above) |
| User agent | `Edibert/<version> (tariff exchange)` |
| Error answer | any `4xx`/`5xx` with body `{"code": "<CODE>", "message": "<text>"}` |
| Rate limit | `429` with `Retry-After` (seconds); the client does not retry on its own |
| Timeout (client) | 20 s |

Client error codes: `EXCHANGE_OFF`, `EXCHANGE_UNREACHABLE` (network, timeout, `5xx`), `EXCHANGE_ACCESS_DENIED`
(`401`, `403`), `EXCHANGE_RATE_LIMITED` (`429`), `EXCHANGE_REJECTED` (other `4xx`; the server `code` is kept),
`EXCHANGE_ANSWER_INVALID` (the answer does not match this contract).

Identifiers:

* `db_id`: `<LAND>/<direction>/<id>`, `LAND` two upper-case letters, `direction` `import`, `export` or `grid`,
  `id` `[a-z0-9_]+` (catalog IDs, see `tariff_identity`; the server assigns IDs for shared tariffs).
* `version`: 64 lower-case hex characters (`tariff_version`, `grid_area_version`).

## 1. Load package

`GET /edibert/v1/packages/{database}/latest`, `database` is `free` or `verified`.

* Both databases are free; no route takes a key or an `Authorization` header.
* `If-None-Match: "<package_id>"` (optional): `304` when that package is still the latest.
* `200`: body is the package file (Catalog P4), header `ETag: "<package_id>"`.
* Errors: `404 NO_PACKAGE`.

The client verifies the file (`verify_package`) and imports it (`plan_package_import`); a conflict is never
resolved without a decision. When to ask: weekly, or when `valid_until` is less than 14 days away. A package
downloaded by hand goes through the same check.

## 2. Submit tariff

`POST /edibert/v1/tariffs`, body:

```json
{"contribution_format": 1, "direction": "import", "tariff": {...}, "version": "<64 hex>",
 "based_on": {"database": "free", "id": "AT/import/x", "version": "<64 hex>"}}
```

* `contribution_format`, `direction`, `tariff`: the P6 payload (`contribution_payload`), unchanged.
* `version`: `tariff_version` of the local tariff. The server recomputes it with the Edibert version it pins
  and rejects a mismatch (`VERSION_MISMATCH`).
* `based_on`: the tariff's `db_ref`, only when it has one.
* Answer `200`: `{"status": "accepted" | "duplicate" | "rejected", "code": <string or null>, "db_id": <string or null>, "version": <string or null>}`.
  `accepted` and `duplicate` carry `db_id` and `version`; `rejected` carries `code`
  (`CONTRIBUTION_FORMAT_UNSUPPORTED`, `TARIFF_INVALID`, `CONTRIBUTION_INDIVIDUAL`, `VERSION_MISMATCH`).
* The client then sets `db_ref = {"database": "free", "id": db_id, "version": version}` on the user tariff.

## 3. Report use

`POST /edibert/v1/usage`, body `{"db_id": "...", "version": "<64 hex>", "pseudonym": "<64 hex>"}`, answer `204`.

* `pseudonym = HMAC-SHA256(install_secret, db_id)` in hex, computed **on the client**. `install_secret` is
  32 random bytes kept in the data folder (`exchange_secret`) and never sent. The pseudonym differs per
  tariff, so the server cannot link the tariffs of one installation.
* Which entries: every tariff in use whose prices equal a database version: a user tariff with `db_ref` and no
  price change since (`differs_from_db` is false), or a catalog tariff of a package catalog.
* **One request per entry, at a random time of the day** (`plan_usage_reports`), never several entries in one
  request. Together with the missing IP log this keeps the entries of one installation apart.
* At most one report per entry and day; the server treats a repeat of the same `(db_id, version, pseudonym)`
  on the same UTC day as a no-op (`204`).
* Errors: `404 UNKNOWN_VERSION` (not in the database), `422 BODY_INVALID`.
* Server rule `reliable`: a version reported by at least two pseudonyms within 12 months (the creator counts).

## 4. Query status

`POST /edibert/v1/status`, body `{"entries": [{"db_id": "...", "version": "..."}, ...]}` (1 to 100 entries, no ID).

Answer `200`: `{"entries": [...]}` in the same order, each

```json
{"db_id": "...", "version": "...", "known": true, "reliable": true, "installations_12m": 3,
 "latest_version": "<64 hex>", "latest_valid_from": "2027-01-01"}
```

`known: false` entries carry only `db_id`, `version` and `known`. `latest_valid_from` is `null` without a
validity date. Ask at most daily.

## 5. Access key (removed)

Until 2026-10-31 the verified database needed an access key (`EDIBERT_ACCESS_KEY`, `Authorization: Bearer`).
Both databases are free now; the client sends no key, and the server ignores an `Authorization` header from
older clients. A catalog is loaded only from the verified database; entries of the free database are templates
the user copies.
