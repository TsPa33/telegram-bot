# Oracle -> Catalogue staging gateway: controlled activation

**Status:** code only. No server, network or Railway changes applied. This workflow intentionally preserves the active bulk import and Warehouse data.

## Prepared components

- Oracle local FastAPI read-only adapter: `catalogue/oracle_adapter/app.py`.
- Oracle local systemd unit: `catalogue/oracle_adapter/carpot-oracle-adapter.service` (binds ONLY 127.0.0.1:8081).
- Optional Catalogue API proxy: `catalogue/oracle_gateway.py`, mounted as additive routes in `catalogue/app.py`.
- Existing Catalogue API and Warehouse behavior remain unchanged with `ORACLE_CATALOGUE_ENABLED=false` (default).
- Tests: `python -m pytest -q catalogue/tests/test_oracle_adapter_stage2.py catalogue/tests/test_oracle_gateway_stage3.py`.

## Real observations (2026-11-22)

- Oracle MySQL 8.4, source database `td1q2018`; `article_li` import was active, `article_links` not complete when reported.
- `article_oe` indexed by (supplierid, datasupplierarticlenumber): supplier 1/article 20064/manufacturer 120 -> OEM 272440, 31256231, 31256232.
- `article_cross` `OENbr` index: OEM 272440/manufacturer 120 returned 10 supplier articles, EXPLAIN uses OENbr (estimated rows: 33).
- `passanger_car_pds` primary begins with passangercarid: 107555 -> PRD 402 and multiple suppliers.
- PRD 402 source description is Russian; any Ukrainian display normalization must preserve the original source record.

**These are cross-references only, not proof of installation suitability or VIN fitment.**

## Before activation on Oracle (operator-controlled; not executed)

1. Confirm that the active bulk import is not at risk, that the Oracle host has enough free RAM/CPU/disk, and that the backup/recovery plan is known.
2. Create a **dedicated** MySQL user, limited to `SELECT` on `td1q2018.*` and local host. Do **not** reuse root or the importer's credentials. For example, after choosing a high-entropy password privately:

   ```sql
   CREATE USER 'carpot_catalogue_ro'@'localhost' IDENTIFIED WITH caching_sha2_password BY '<GENERATE_A_NEW_SECRET_ON_ORACLE>';
   GRANT SELECT ON td1q2018.* TO 'carpot_catalogue_ro'@'localhost';
   SHOW GRANTS FOR 'carpot_catalogue_ro'@'localhost';
   ```

   This changes the MySQL user/grant metadata, so perform it only after the importer impact window is approved. Never paste actual credentials into chat.
3. Use a separate unprivileged Linux service account `carpot-oracle-api`, place the adapter code and an isolated Python 3.12 venv under `/opt/carpot/oracle-adapter`, and put its secret environment file at `/etc/carpot/oracle-adapter.env` with mode `0600` root-owned. Required variables: `ORACLE_MYSQL_HOST=127.0.0.1`, `ORACLE_MYSQL_PORT=3306`, `ORACLE_MYSQL_DATABASE=td1q2018`, `ORACLE_MYSQL_USER=carpot_catalogue_ro`, `ORACLE_MYSQL_PASSWORD`, `ORACLE_ADAPTER_KEY` (a new independent secret).
4. Install the systemd unit and inspect `systemctl status`. It must listen only at `127.0.0.1:8081`. Test with three bounded read-only requests on localhost. Do not configure a public adapter domain until access controls and TLS have been verified.
5. Arrange protected **HTTPS** transport from Railway to the Oracle-local adapter (e.g. approved TLS reverse proxy with network restrictions). Do not open MySQL port 3306. A raw IP/HTTP URL is intentionally rejected by the Catalogue gateway. DNS/TLS endpoint details have not been supplied, so the network path is **not** currently provisioned.
6. In Railway `catalogue-staging` only, after the endpoint is reachable and credentials stored securely, set:
   - `ORACLE_CATALOGUE_ENABLED=true`
   - `ORACLE_ADAPTER_URL=https://<approved-hostname>`
   - `ORACLE_ADAPTER_KEY=<same-independent-secret>`
   - Automatically supplied `RAILWAY_ENVIRONMENT_NAME` must equal `catalogue-staging`.
7. Deploy only the approved staging Catalogue branch; verify previous `/health`, `/api/v1/oem`, `/api/v1/articles/oem` still work. Compare read-only Oracle routes against actual OEM samples. Keep Warehouse writes and auto OEM source unchanged until a separate fitment proof.
8. If any failure occurs, set `ORACLE_CATALOGUE_ENABLED=false`, and leave Warehouse/production untouched.

## Staging route map

All routes require the existing `X-Catalogue-Key` and refuse requests when not activated:
- GET `/api/v1/oracle/oem/by-article?supplier_id=1&article_number=20064&manufacturer_id=120`
- GET `/api/v1/oracle/oem/by-number?manufacturer_id=120&oem_number=272440`
- GET `/api/v1/oracle/vehicles/107555/prd`

Additional safeguards: explicit HTTPS URL, no redirect-following, short timeouts, 96 KiB payload limit, strict schema validation, 1–50 response rows, `fitment_verified=false`. No `article_li` or `article_links` usage.

## Known blockers

- No authenticated administrative execution interface to Oracle was connected to this chat, so reader/user/service setup is not executed.
- No DNS hostname, certificate, or private Railway-to-Oracle transport is specified; do not invent one.
- `article_links` and `article_li` completion and indexes require re-verification before exact vehicle fitment work.
- Only simulated tests, **not** live end-to-end service requests, have been executed.
