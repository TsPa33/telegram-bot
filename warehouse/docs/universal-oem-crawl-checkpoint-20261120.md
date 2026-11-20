# CarPot Universal OEM — checkpoint, 2026-11-20

## Confirmed from live staging
- Catalogue PR #562, Warehouse API PR #563, frontend PR #564 were successfully deployed to **staging**.
- Local MySQL source `td1q2018` on the user's Windows host is **not reachable from Codex/GitHub/Railway**.
- Measured baseline from authenticated Warehouse diagnostic: XC60 VIN `YV4L12RK6N1970668` 0/595 OEM; XC90 VIN `YV4A22PK2G1092943` 16/196 valid plan OEM refs; DAF `XLRTE47MS0E774889` 0/227 OEM.
- The existing 7 Catalogue snapshots (XC90 + six 2017+ XC60 variants) do not prove exact fitment for a 2022 VIN.
- Previous Codex session imported **zero additional graphs** from Windows; the new frontend only displays `OEM уточнюється`.

## Work added by PR #565
- `catalogue/vehicle_source_batch.py discover`: SELECT-only keyset discovery across all passenger-car modifications by primary-key cursor, exact `article_links.linkagetypeid=2` probe. Returns bounded JSON pages; no input VIN or modification IDs.
- `--omit-prd-export`: avoids exporting the entire PRD table into every per-vehicle graph (this would otherwise make an all-make run infeasible).
- `catalogue/transfer-oem-graph.ps1`: without `-ModificationId` automatically scans all passenger modifications, exports one graph per linked identity and can optionally upload to Catalogue staging. Staging write still requires externally verified `@@server_uuid`, explicit `-ApplyToStaging`, and the local SSH tunnel; no silent writes. Export and staging cursors are separate.
- `catalogue/tests/test_vehicle_source_batch.py`: synthetic test coverage for discovery and no redundant full PRD dump.
- No production deployment or local MySQL interaction was performed from ChatGPT.

## Next Windows action
Repository checkout must contain PR #565. Source-only discovery/export:
```powershell
cd C:\CarPot\telegram-bot
git fetch origin feature/carpot-oem-automatic-passenger-crawl-20261120
git switch --create feature/carpot-oem-automatic-passenger-crawl-20261120 --track origin/feature/carpot-oem-automatic-passenger-crawl-20261120
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\catalogue\transfer-oem-graph.ps1
```
If a local checkout already has uncommitted changes, stop before `git switch` and preserve them. If the branch already exists locally, switch to it without `--create`.
Local root MySQL previously accepted an empty password. If that has changed, use `-PromptSourcePassword`. The script persists data under `%LOCALAPPDATA%\CarPot\OEM-graph-all`; re-running continues via the keyset cursor.

**This runs a potentially large SELECT-only export on the user's own Windows computer; it will not complete instantly.**
Staging upload requires verified MySQL server UUID and an open `railway.cmd connect MySQL ... --tunnel-only` tunnel. Do not substitute production credentials.

## Remaining blockers
1. Execute the full crawl on Windows and upload graphs through the guarded staging tunnel. Count imported modifications, source links, OEM numbers, skipped records and source issues.
2. Inspect source commercial/truck schema to determine the correct linkage type for DAF; passenger `linkagetypeid=2` is **not** a truck importer.
3. Implement tested high-confidence historical Warehouse row matching without inventing VIN modification identity, position, or source PRD ID. Maintain manual OEMs and physical stock/quantities.
4. Re-run authenticated admin coverage report, confirm OEM fields in XC60 #31 and XC90; report measured before/after. Do **not** claim 100% from frontend state or API health.

Security: Railway MySQL root credential was previously exposed in a screenshot; rotate it in a controlled window and update dependent integrations.
