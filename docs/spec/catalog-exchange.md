# Catalog exchange with the tariff database server (contract v2)

Technical contract between the Edibert client (`src/edibert/exchange.py`) and the tariff database server.
The server is not part of this repository; this file is the contract both sides build against. Package
format and import: [tariff-format.md](tariff-format.md) section 11. Payload of a shared tariff: `edibert.contribution`.

**Contract v2** (`0.1.d` D3, 2026-10-31) replaces the two databases (free and verified) of v1 with **one** tariff
database in which every version carries a check state. v1 was never used by a published client; its package
paths `/packages/free/latest` and `/packages/verified/latest` are gone, not redirected.

## Model

* **One database, one ID space.** Every tariff (later every grid area) has a database ID and versions. Catalog IDs
  of the seed and IDs the server assigns to shared tariffs (`shared_…`) live side by side; an ID is never renamed.
* **Per version** three independent properties:

  | Property | Values | Set by |
  |---|---|---|
  | `check_state` | `unchecked`, `checked` (with date and source), `released_by_supplier` (with date and releasing party), `rejected` | moderation; `released_by_supplier` on an e-mail of the supplier or network operator |
  | `reliable` | `true` / `false`, with `installations_12m` | computed from use reports (route 3) |
  | lifecycle | current, superseded (a newer version exists), blocked (moderation removed it), merged into another ID | server, moderation |

* **Trust level** for display, derived on the client and never stored: `released_by_supplier` > `checked` >
  `reliable` > `unchecked` (`edibert.trust.trust_level`).
* **Two views**, both free, no key:
  * **Catalog** (route 1): the current `checked` and `released_by_supplier` versions as one signed package. A
    signed package never carries an unchecked version.
  * **Templates** (route 5): the other versions moderation admitted, unsigned, per land and direction. The client
    shows them only after an opt-in and only copies them into the user's own tariffs; a template is never
    imported as catalog.
* **Promotion instead of a move:** when moderation checks a shared version, the same ID and version become
  `checked`. A user who copied it sees "checked version available" in the status of the copy (route 4).
* **Supplier release:** a supplier releases a version that is already in the database by e-mail from its company
  domain, naming database ID and version. The server records it without an extra check; it holds for exactly that
  version and never expires. The supplier may withdraw it at any time; the version then falls back to `checked`
  and stays in the catalog until moderation checks it again.
* **Check overdue:** a `checked` or `released_by_supplier` version whose check date is older than the check
  interval (target quarterly, 91 days) plus 30 days is shown as "check overdue"; a grid fee also when 1 January
  has passed and its check date is from an earlier year (`edibert.trust.check_overdue`).

## Principles

* **Edibert computes locally and offline.** The server only delivers packages and templates and counts use. An
  outage, a slow answer or a wrong answer never changes a price; every exchange runs beside the calculation.
* **Hard off switch:** `EDIBERT_EXCHANGE_OFF=1` stops every request, whatever a host configured
  (`EXCHANGE_OFF`). A host (Earnie) builds its own `ExchangeConfig` and asks for its own consent.
* **No installation ID**, on any route. Edibert never sends one; a host must not add one.
* **No IP log** on the routes `usage`, `status` and `templates`: the server and its reverse proxy keep no client
  address for them (no access log line with IP, no rate-limit table kept longer than the limit window).
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
| Keys | none; no route takes a key or an `Authorization` header |

Client error codes: `EXCHANGE_OFF`, `EXCHANGE_UNREACHABLE` (network, timeout, `5xx`), `EXCHANGE_ACCESS_DENIED`
(`401`, `403`), `EXCHANGE_RATE_LIMITED` (`429`), `EXCHANGE_REJECTED` (other `4xx`; the server `code` is kept),
`EXCHANGE_ANSWER_INVALID` (the answer does not match this contract).

Identifiers:

* `db_id`: `<LAND>/<direction>/<id>`, `LAND` two upper-case letters, `direction` `import`, `export` or `grid`,
  `id` `[a-z0-9_]+` (catalog IDs, see `tariff_identity`; the server assigns IDs for shared tariffs).
* `version`: 64 lower-case hex characters (`tariff_version`, `grid_area_version`).
* `db_ref` (on a user tariff, in `based_on`): `{"id": "<db_id>", "version": "<64 hex>"}`. v1 carried a third
  key `database`; a file with it is migrated explicitly (`tariff-format.md` section 11, `DB_REF_LEGACY`).

## 1. Load catalog package

`GET /edibert/v1/packages/catalog/latest`

* `If-None-Match: "<package_id>"` (optional): `304` when that package is still the latest.
* `200`: body is the package file (package format 2, `tariff-format.md` section 11), header `ETag: "<package_id>"`.
* Errors: `404 NO_PACKAGE`.

The client verifies the file (`verify_package`) and imports it (`plan_package_import`); a conflict is never
resolved without a decision. When to ask: weekly, or when `valid_until` is less than 14 days away. A package
downloaded by hand goes through the same check.

## 2. Submit tariff

`POST /edibert/v1/tariffs`, body:

```json
{"contribution_format": 1, "direction": "import", "tariff": {...}, "version": "<64 hex>",
 "based_on": {"id": "AT/import/x", "version": "<64 hex>"}}
```

* `contribution_format`, `direction`, `tariff`: the P6 payload (`contribution_payload`), unchanged.
* `version`: `tariff_version` of the local tariff. The server recomputes it with the Edibert version it pins
  and rejects a mismatch (`VERSION_MISMATCH`).
* `based_on`: the tariff's `db_ref`, only when it has one. It may name **any** entry, a shared one or a catalog
  entry. When it names an existing entry of the same land and direction, the submission becomes a new version of
  that entry (a changed price of a checked catalog tariff arrives at the right entry); when that entry was merged,
  of the entry it was merged into. Otherwise, or without `based_on`, a new entry starts, unless the same version
  of the same supplier exists already (`duplicate`).
* A new version is `unchecked` and waits for moderation; it never enters the catalog without a check.
* Answer `200`: `{"status": "accepted" | "duplicate" | "rejected", "code": <string or null>, "db_id": <string or null>, "version": <string or null>}`.
  `accepted` and `duplicate` carry `db_id` and `version`; `rejected` carries `code`
  (`CONTRIBUTION_FORMAT_UNSUPPORTED`, `TARIFF_INVALID`, `CONTRIBUTION_INDIVIDUAL`, `VERSION_MISMATCH`,
  `MODERATION_REJECTED`).
* The client then sets `db_ref = {"id": db_id, "version": version}` on the user tariff.

## 3. Report use

`POST /edibert/v1/usage`, body `{"db_id": "...", "version": "<64 hex>", "pseudonym": "<64 hex>"}`, answer `204`.

* `pseudonym = HMAC-SHA256(install_secret, db_id)` in hex, computed **on the client**. `install_secret` is
  32 random bytes kept in the data folder (`exchange_secret`) and never sent. The pseudonym differs per
  tariff, so the server cannot link the tariffs of one installation.
* Which entries: every tariff in use whose prices equal a database version: a user tariff with `db_ref` and no
  price change since (`differs_from_db` is false), or a catalog tariff of an imported package catalog.
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
{"db_id": "...", "version": "...", "known": true,
 "check_state": "checked", "checked_at": "2026-11-02",
 "reliable": true, "installations_12m": 3,
 "latest_version": "<64 hex>", "latest_valid_from": "2027-01-01",
 "latest_checked_version": "<64 hex>",
 "merged_into": null}
```

* `known: false` entries carry only `db_id`, `version` and `known` (the version is not in the database, or
  moderation blocked it).
* `check_state`: of the asked version. `checked_at`: the date of that state (our check for `checked`, the
  release for `released_by_supplier`); `null` for `unchecked` and `rejected`.
* `latest_version`, `latest_valid_from`: the newest version of the entry (latest validity start, then latest
  added), whatever its check state; `latest_valid_from` is `null` without a validity date.
* `latest_checked_version`: the newest `checked` or `released_by_supplier` version of the entry, `null` when there
  is none. When it differs from `version`, the client shows "checked version available".
* `merged_into`: `null`, or `{"db_id": "<target>", "version": "<64 hex>"}` when moderation merged this entry into
  another one: the target's version with the same prices when it has one, else its newest version. The client
  re-links a copy to it only after the user confirmed.

Ask at most daily.

## 5. List templates

`GET /edibert/v1/templates?land=AT&direction=import[&grid_area=<id>][&supplier=<text>]`

* `land` (two letters) and `direction` (`import`, `export`, `grid`) are required. `grid_area` only with
  `direction=grid`: the local part of the grid area's database ID. `supplier`: case-insensitive search in the
  supplier ID and the label, at least 2 characters. Anything else is `422 BODY_INVALID`.
* Content: every version moderation admitted that is not `checked`, `released_by_supplier` or `rejected`, of an
  entry that was not merged, sorted by supplier ID, label, `db_id` and validity start; at most 200
  (`truncated: true` above).
* Answer `200`:

```json
{"templates": [{"db_id": "AT/import/shared_x", "version": "<64 hex>", "direction": "import",
                "tariff": {...}, "valid_from": null, "check_state": "unchecked",
                "reliable": false, "installations_12m": 1,
                "latest_version": "<64 hex>", "latest_checked_version": null}],
 "truncated": false}
```

* `tariff` is the P6 payload tariff (no `id`); the client copies it as a user tariff with
  `db_ref = {"id": db_id, "version": version}` and checks that the version it computes matches (`EXCHANGE_ANSWER_INVALID`
  otherwise).
* Grid areas are not in the database yet (`0.1.d2`): `direction=grid` answers an empty list.

## 6. Moderation (server side, not a route)

The server CLI sets the check state; it is not reachable over HTTP. Commands (earnie-server `tariff_db`):

* **check** `<db_id> <version> --source <text> [--at <date>]`: `checked` with date and source.
* **reject-check** `<db_id> <version> --source <text>`: `rejected` (checked against the source and wrong).
* **release** `<db_id> <version> --by <party> [--at <date>]`: `released_by_supplier`.
* **withdraw** `<db_id> <version>`: back to `checked`; the date and source of our own check stay, or, when we never
  checked it, the release date with the source "supplier release, withdrawn".
* **merge** `<source db_id> <target db_id>`: the source entry is merged into the target; its versions stay
  known (route 4 names the target) but leave the templates.

## Changes from v1

| v1 | v2 |
|---|---|
| `/packages/{free\|verified}/latest` | `/packages/catalog/latest` |
| `db_ref` / `based_on` `{database, id, version}` | `{id, version}` |
| `based_on` only for entries of the free database | for any entry |
| route 4 `known`, `reliable`, `installations_12m`, `latest_version`, `latest_valid_from` | plus `check_state`, `checked_at`, `latest_checked_version`, `merged_into` |
| templates: the free database package | route 5 |
| package format 1 with `manifest.database` | package format 2, one catalog |
