# CarPot Oracle Catalogue Adapter — Stage 2 (2026-11-22)

## Scope
Standalone **internal** FastAPI service on a separate feature branch. **Not deployed**, not connected to live Railway Catalogue or Warehouse.

Grounded Oracle MySQL evidence:
- article_oe: supplierid compound index (supplierid, datasupplierarticlenumber); supplier 1, article 20064, manufacturer 120 yields OEM 272440, 31256231, 31256232.
- article_cross: OENbr index; EXPLAIN for manufacturer 120 and OEM 272440 selected OENbr, approximately 33 examined rows. At least 10 supplier article links were retrieved.
- passanger_car_pds: PRIMARY begins with passangercarid; car 107555 returned nodeid 100030, productid 402 with multiple suppliers.
- PRD 402: "Комплект тормозных колодок, дисковый тормоз". Proposed Ukrainian display name: "Комплект гальмівних колодок дискового гальма". Preserve original source text.

**Source links are not verified VIN fitment or confirmed interchangeability.** Never silently assign source OEM to unrelated stock parts. The pending article_links and actively importing article_li must not be queried.

## API contract
All routes except /health require X-Oracle-Adapter-Key.
- GET /api/v1/oracle/oem/by-article?supplier_id=1&article_number=20064&manufacturer_id=120
- GET /api/v1/oracle/oem/by-number?manufacturer_id=120&oem_number=272440
- GET /api/v1/oracle/vehicles/107555/prd
- GET /health (process health only, does NOT check live MySQL)

All results expose fitment_verified=false; max 50 rows, truncated=true when at least one more row was observed. No endpoint provides complete VIN/vehicle-fitment coverage.

Queries use the verified existing indexes (FORCE INDEX), bound SQL parameters, server-side execution limit 3000 ms, short socket timeouts, explicit read-only MySQL sessions, plus a mandated restricted MySQL account. No writes/DDL, imports, source changes or paid API calls.

## Required environment (do not commit values)
- ORACLE_ADAPTER_KEY: a unique randomly generated internal API secret
- ORACLE_MYSQL_HOST=127.0.0.1 (on Oracle host or through an independently secured localhost private tunnel)
- ORACLE_MYSQL_PORT=3306 on Oracle host, or actual local tunnel port
- ORACLE_MYSQL_USER: dedicated MySQL SELECT-only account. root/admin explicitly rejected.
- ORACLE_MYSQL_PASSWORD: stored in secret manager, never in Git or chat
- ORACLE_MYSQL_DATABASE=td1q2018

MySQL read-only identity and verified SELECT grants are required before any live adapter start. Do not create or change DB users while the large import is active without approval. The current importer uses sudo mysql; its session should not be modified.

## Offline tests
From repository root:

    python -m pip install -r catalogue/oracle_adapter/requirements.txt
    python -m pip install pytest httpx
    python -m pytest -q catalogue/tests/test_oracle_adapter_stage2.py

Author's local verification: 5 passed, with fake database responses. This is not live Oracle E2E acceptance.

## Release gates
1. Confirm dedicated restricted MySQL account, real grants, and local Oracle connectivity.
2. Run three bounded probes and inspect live query plans on Oracle.
3. Choose approved private Railway-to-Oracle network transport. Never expose MySQL port 3306 or adapter on public plain HTTP. Use TLS (prefer private network), API secret, ingress allowlist and request controls.
4. Add a separate opt-in Catalogue client and feature flag in staging, preserving existing MySQL fallback. No pre-deploy bootstrap.py against Oracle.
5. Verify Volvo OEM 272440 API results and read-only logging in staging.
6. Only after article_links finishes and exact source fitment mapping is validated, design the full vehicle/part article graph for OEM-to-Warehouse assignment.
7. Preserve seller-set OEM values, stock quantities, source provenance and production.

Do not deploy this branch or connect it to existing Railway services before steps 1–3 are complete.

## Modification audit

The adapter and the staging-only Catalogue gateway use the same GET paths:

- `/api/v1/oracle/vehicles/{car_id}/audit?kind=passenger`
- `/api/v1/oracle/vehicles/{car_id}/articles?kind=passenger&offset=0&limit=20`
- `/api/v1/oracle/vehicles/{car_id}/oem?kind=passenger&offset=0&limit=20`

`kind` is required and accepts `passenger` or `commercial`. Each page uses
`next_offset` for continuation and accepts limits from 1 to 50. Manufacturer ID
is resolved from the modification and model in the requested catalogue.

PRD link and part-type counts come from the catalogue's PDS table. A unique
article is the supplier ID and exact article number. OEM coverage uses exact
article matches for the resolved manufacturer. Category IDs are source PDS
node IDs matched by supplier and product. A null category groups articles
without a matching node, and an article can appear in multiple nodes.
Coverage is null when there are zero articles.

The audit reads `article_links` using the `linkageid` index and inherits the
existing read-only session and 3-second statement limit. Before installing the
adapter update on Oracle, verify that the link import is complete, SELECT
access is present, and the live query plans use the expected indexes. The
commercial audit requires confirming the source table
`commercial_vehicle_pds(commercialvehicleid, nodeid, productid, supplierid)`,
its leading primary key, and the commercial link discriminator. Set
`ORACLE_COMMERCIAL_LINKAGE_TYPE` on the adapter to the verified value.
The gateway can be deployed separately and returns 503 while the upstream
audit routes are unavailable.
