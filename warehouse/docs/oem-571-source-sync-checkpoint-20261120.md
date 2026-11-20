# CarPot — Universal OEM source synchronization, stage 571
Date: 2026-11-20. Scope: staging only.

## Source proof (user-provided archive)
- Local Windows MySQL: `td1q2018`, localhost:3306; source login `root` previously worked **without a password**.
- User-provided diagnostic zip contained schema metadata of 60 tables; estimates: `article_links` ~211.6m rows, `article_oe` ~19.7m rows, `passanger_cars` ~68k, `commercial_vehicles` ~20k.
- For XC60 II source model `37773`, six source modifications were previously exported: 126478, 126479, 126480, 126481, 126482, 128114. The sample `126480` contains 54 source PRDs, 233 article keys and 353 OEM rows (135 differently spelled numbers).
- Live Warehouse staging source-modification selection for donor 39 = 126480. Current persisted diagnostic: 591 eligible stock rows, 14 with OEM, 571 without a verified PRD binding, 6 mapped without OEM. **Do not claim complete OEM coverage**.
- Manufacturer/model names carry TecDoc platform suffixes (e.g. `XC60 II (246)`); Catalogue PR #570 and Warehouse PR #569 previously repaired those filters.

## Implemented in PR #571
- Keyset `discover` now supports `--model-id` (source model ID) so that the first actual Windows source transfer can target XC60 without manual VIN/modification ID enumeration.
- A separate checkpoint under `%LOCALAPPDATA%\CarPot\OEM-graph-all\model-37773` prevents a model pilot from advancing the all-make source cursor.
- Existing SELECT-only `export --graph-only --with-oem --omit-prd-export` and verified snapshot importer remain the only mutation path; writing to Catalogue staging requires `-ApplyToStaging`, a different localhost port, staging tunnel, independently checked `@@server_uuid`, and an explicit password.
- `commercial-audit` performs SELECT-only schema and bounded linkage sampling for DAF and other trucks, without guessing `linkagetypeid=2` (passenger only). The full passenger scan performs this audit automatically.
- Tests added for source model-keyset filtering, exact fitment gate, commercial audit read-only behavior. Production unchanged.

## ONE Windows command — source-only scoped export
Use the existing Windows checkout, without hardcoding any database passwords:
```powershell
cd C:\CarPot\telegram-bot
git status --short
git fetch origin feature/carpot-oem-source-model-sync-20261120
git switch --track origin/feature/carpot-oem-source-model-sync-20261120
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\catalogue\transfer-oem-graph.ps1 -ModelId 37773
```
If local branch already exists: `git switch feature/carpot-oem-source-model-sync-20261120`. If worktree has uncommitted changes, preserve them first. If MySQL has a non-empty password use `-PromptSourcePassword`.

Expected marker: `PASSENGER GRAPH CRAWL COMPLETE`. All graph artifacts remain on Windows, default directory `$env:LOCALAPPDATA\CarPot\OEM-graph-all\model-37773`. A rerun resumes from the same cursor.

## Next steps after source-only success
1. Inspect actual output: source modifications, valid OEM references, hashes and any failures. Do not interpret a successful shell exit as filled Warehouse fields.
2. Open **Catalogue staging MySQL tunnel only** using `railway.cmd connect MySQL --project ff2f3a14-2ffa-49ba-9b9d-9889ce98da5d --environment catalogue-staging --tunnel-only --port 50212` in a separate PowerShell window.
3. Confirm the destination database identity independently, use `-ApplyToStaging -ModelId 37773 -TargetServerUuid <verified UUID>`. Never paste the DB password in chat.
4. Compare Catalogue inventory + Warehouse OEM admin coverage before/after; no manual resets of donor 39.
5. Expand to all passenger makes with the same script **without `-ModelId`** once selective import proves healthy. Commercial graph needs confirmed linkage metadata and a separate source adapter.
6. Architecturally retire the legacy 595-position base plan for *new* catalogue-native donors; import alone cannot give 591 correct OEMs from 54 source PRDs. Preserve existing stock until explicit reconciliation.

## Constraints
Not possible for ChatGPT tools to query localhost Windows MySQL directly. User must run the source read-only sync locally once. This PR does not claim full import or complete fitment. No paid APIs, database deletions, or production changes.
