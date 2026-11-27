# CarPot Aleto worker for Oracle Linux

The worker runs from the Warehouse backend on Python 3.12. It uses a dedicated SQLite database in `/var/lib/carpot-market-reference` and serves loopback health on port 8731. It requires HTTPS access to Aleto and a systemd host. Run the installer commands only after verifying the target, disk space, backup and isolation.

Install the reviewed Warehouse backend into `/opt/carpot-aleto-parser/backend` with root-owned code and read access for the service account. From the reviewed checkout:

```sh
sudo python3.12 -m venv /opt/carpot-aleto-parser/venv
sudo /opt/carpot-aleto-parser/venv/bin/pip install -r warehouse/backend/requirements.txt
sudo install -m 0644 warehouse/deploy/oracle/carpot-aleto-parser.conf /etc/sysusers.d/carpot-aleto-parser.conf
sudo systemd-sysusers /etc/sysusers.d/carpot-aleto-parser.conf
sudo install -m 0644 warehouse/deploy/oracle/carpot-aleto-parser.service /etc/systemd/system/carpot-aleto-parser.service
sudo systemctl daemon-reload
sudo systemctl enable --now carpot-aleto-parser
sudo systemctl is-active carpot-aleto-parser
curl --fail http://127.0.0.1:8731/healthz
```

From the installed backend, use the service account for queue commands so database, journal and lock files have consistent ownership:

```sh
cd /opt/carpot-aleto-parser/backend
sudo -u carpot-aleto-parser /opt/carpot-aleto-parser/venv/bin/python -m app.aleto_worker \
  --database /var/lib/carpot-market-reference/catalogue.sqlite3 create Acura MDX --year 2022
```

Use the same command prefix with `show JOB_ID`, `choose JOB_ID CANDIDATE_URL`, `pause JOB_ID`, `resume JOB_ID`, `cancel JOB_ID`, `retry JOB_ID` and `results JOB_ID`. Results are newline-delimited JSON observations. Candidate URLs are restricted to those discovered for the job. Review every candidate against the requested vehicle before choosing it.

`parser_jobs` stores input, discovery decisions and job state. `parser_queue` records URL checkpoints, per-page status and extraction issue counts. `market_observations` stores observations by job, page and source article. The worker commits observations and their page checkpoint together. Restarting retries the first uncommitted page and retains committed results. It caps each job at 1000 listing pages and checks robots before fetching. A blocked or failed request stops the current job for operator review.

A live acceptance check should verify health, confirm a discovered catalogue, pause after progress, restart systemd, resume, and compare the committed URL and article counts before and after restart. The loopback health check confirms service availability. Inspect job status separately to verify Aleto connectivity. Preserve the dedicated SQLite store and its WAL when arranging backups.


## Warehouse staging control and rollout

1. Verify the Oracle host identity, SSH access, space, OS, Python 3.12, systemd and HTTPS connectivity. Record MySQL and Oracle Adapter health and confirm a current backup. Preserve any existing Aleto state with SQLite's backup API. Install the backend and parser unit using the commands above.
2. Create root-owned mode 0600 `/etc/carpot-aleto-control.env` through the host's secret provisioning, with `CARPOT_ALETO_TOKEN` set to a unique random token of at least 32 ASCII characters. Install `carpot-aleto-control.service`, `carpot-aleto-refresh.service` and `carpot-aleto-refresh.timer` in `/etc/systemd/system/` at mode 0644. Run `sudo systemctl daemon-reload` and `sudo systemctl enable --now carpot-aleto-control.service carpot-aleto-refresh.timer`. Verify the new unit states with `systemctl is-active` and the worker health on port 8731. The timer checks hourly for explicitly opted-in jobs due for a daily refresh. A failed refresh requires operator review and retry before its schedule advances.
3. Connect Railway Warehouse staging to the loopback control API on port 8732 over the approved private TLS relay. Keep the raw port loopback-bound. Pass the Authorization header through the relay and restrict relay access to staging. Set `WAREHOUSE_ALETO_WORKER_URL` to the TLS endpoint and `WAREHOUSE_ALETO_WORKER_TOKEN` to the matching secret in the Warehouse API staging service. The API gateway injects the authenticated workspace and actor. Check that unauthenticated access returns 401.
4. Verify that staging runs the reviewed integration SHA with the staging database binding and that the current backup is restorable. Deploy Warehouse API, then Web. Apply the Warehouse API release through its existing migration entry point, with PostgreSQL head `a20261127001`. The two new Warehouse tables store import checkpoints and batch reports. Oracle schema additions apply only to the dedicated Aleto SQLite file. The existing Warehouse import preview and confirmation routes control publication. Import preparation is restricted to the Railway environment named `warehouse-staging`, and requires the existing platform-owner allowlist.
5. As a staging owner, go to Administration → Catalogue → Parser jobs. Decode both acceptance VINs, review the Oracle candidates, and create a third task by make and model. Select a confirmed Aleto catalogue, observe growing processed/queued counts, pause, restart the parser unit, resume, and validate a result. Prepare the completed result, run preview in Market Prices and review changes before confirming the staging import. Compare existing stock and sale prices before and after. Check MySQL and Oracle Adapter health again.
6. To take Aleto offline, remove the staging worker variables and stop `carpot-aleto-refresh.timer`, `carpot-aleto-refresh.service`, `carpot-aleto-control.service` and `carpot-aleto-parser.service`. Keep the dedicated SQLite file for recovery. Restore the previous Warehouse staging deployment if needed.

Access uses Warehouse team permissions `catalog_parser_view`, `catalog_parser_manage`, `catalog_parser_publish` and `catalog_parser_admin`. The existing owner confirmation still governs global publication. SQLite records action, actor, job and time. A refresh creates a new job with the previous catalogue URLs and preserves earlier observations. The Warehouse import preview determines which changes may be published.

## Large result acceptance

- Complete a job before preparing its import. The Warehouse owner processes batches of at most 500 observations. Each transaction stores the upload, per-record outcome, and the next source cursor. After closing the UI or losing a request, reopen the job and select “Підготувати / продовжити імпорт”. The report includes rejected entries and the existing Warehouse preview/apply state per batch. Review and confirm each batch independently.
- In results, apply the desired search and sort, then request “Підготувати повний CSV”. The parser process builds the export in the background in `/var/lib/carpot-market-reference/exports`, using all matching rows through the captured source row ID. An empty search exports every captured row. Keep this directory on the Aleto state volume and include it in capacity monitoring.
- Verify MySQL and Catalogue Adapter health before and after enabling the Aleto units. Use the host's existing approved read-only health checks and compare the unit states, restart counts and health responses. The Aleto units use a separate service user, code path, SQLite file and loopback ports. Their unit definitions contain no MySQL or Catalogue Adapter lifecycle commands, and mask standard MySQL paths. Oracle installation and rollback concern only `carpot-aleto-*` units.
- Keep PostgreSQL migration `a20261127001` in place during an application rollback to preserve the import reports. Schedule a DB schema downgrade independently if required and after backup review.
