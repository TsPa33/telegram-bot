# CarPot Catalogue — independent staging MVP

This module is isolated from /warehouse and production. It uses its own MySQL database in Railway `catalogue-staging`.

## Scope
- Read-only API: GET /health, GET /api/v1/parts?q=..., GET /api/v1/oem?number=...
- API search requires header `X-Catalogue-Key`, configured via `CATALOGUE_API_KEY`. Without it, all search requests fail closed.
- Two compact tables: `catalogue_parts` and `catalogue_oem`.
- Bounded local pilot transfer of up to 5,000 Volvo OEM references via pilot_import.py.
- No copying 50 GiB and no modification to local source.

## Database initialization
The `catalogue-api` pre-deploy command executes `python bootstrap.py` against the newly provisioned Railway MySQL database specified by `MYSQLDATABASE` (usually `railway`). Schema creation is idempotent. Do not point it at production.

## Pilot transfer
On Windows, install Python and `pip install -r requirements.txt`. Keep local MySQL running.
Use Railway CLI `railway connect MySQL --tunnel-only` from the correct project/environment to open a local TCP tunnel (use its reported port).
Set SOURCE_HOST=127.0.0.1, SOURCE_PORT=3306, SOURCE_USER, SOURCE_PASSWORD (empty if local root has none).
Set DEST_HOST=127.0.0.1, DEST_PORT=<tunnel-port>, DEST_USER, DEST_PASSWORD, DEST_DATABASE=railway (or `catalogue` only if you explicitly created and configured that database).
Set PILOT_MAX_ROWS=1000, then `python pilot_import.py`.
Do not paste database secrets into a chat or commit them to Git.
A tunnel avoids opening public MySQL access. Read the Railway tunnel instructions for the actual local port.

## Limits
Source table `article_oe` contains confirmed OEM references; source table `articles` contains confirmed names. Other datasets (images, prices, vehicle-fitment, tree categories, modifiers) are NOT confirmed ready to import. Some passenger_* reads currently return MySQL error 1146; do not import these until their metadata/files are diagnosed on a backed-up copy.
Source records may require licensing permission before use in a commercial service.

## Selective resumable importer

The Windows-only script `selective_import.py` is the next stage after `pilot_import.py`.
It reads only the local `td1q2018` database, writes to isolated Railway staging and keeps
per-job resume checkpoints in `.import_state` after each committed batch.
It does not transfer 50 GiB or alter CarPot Warehouse.

Jobs: `manufacturers`, `models`, `volvo-oem`.
The last job uses Volvo OEM manufacturer ID 120 and can be slower due to the large source tables.
Do not attempt a full import before measuring its performance.
It only transfers known fields, not images, prices, categories, fitment or translations.

From an existing PowerShell session with SOURCE_* and DEST_* settings,
local MySQL running, and Railway MySQL tunnel open:

```powershell
cd C:\CarPot\Catalogue
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/TsPa33/telegram-bot/feature/carpot-catalogue-mvp/catalogue/selective_import.py" -OutFile "selective_import.py"
python -u .\selective_import.py --job manufacturers --max-rows 5000 --batch-size 250 --confirm-staging
python -u .\selective_import.py --job models --max-rows 5000 --batch-size 250 --confirm-staging
```

Re-run the models command to proceed from its saved position.
For OEM, first test with `--job volvo-oem --max-rows 250 --batch-size 100 --confirm-staging`.
Each invocation is bounded to at most 20,000 records and uses a destination metadata
size guard of 3500 MiB. This is not a guaranteed physical disk usage measurement.
Maintain backups; do not remove `.import_state` or run overlapping jobs.
Existing source metadata errors involving `passenger_*` remain outside this release.

## Full articles/OEM import (all manufacturers)

`full_import.py` is a separate Windows importer. It NEVER updates source `td1q2018`. Two jobs:
`articles` copies all article identities and names; `oem` copies all original-number mappings.
The destination retains only necessary columns. Checkpoints are written in
`railway.catalogue_import_progress` within the **same transaction** as each batch.

The importer tests for a matching leftmost compound index on the local source table
before attempting large reads. If the required OEM index does not exist, it stops
safely with a list of available indexes: do NOT create an index on the 50-GiB
source without a backup. Local source ordering must remain unchanged during import.

Download from the `feature/carpot-catalogue-mvp` branch and run in the existing
PowerShell session that has SOURCE_* / DEST_* variables and an active SSH tunnel:

```powershell
cd "C:\CarPot\Catalogue"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/TsPa33/telegram-bot/feature/carpot-catalogue-mvp/catalogue/full_import.py" -OutFile "full_import.py"
python -u .\full_import.py --job articles --preflight --confirm-staging
python -u .\full_import.py --job oem --preflight --confirm-staging
```

Only after preflight and confirmation of available Railway storage, run
`--job articles --max-rows 20000 --batch-size 500 --confirm-staging`
and repeat. Once all articles are done, import OEM in the same manner.
You can raise `--max-rows` to 200000 per run; it is a *per-run safety bound*,
not a global catalogue size limit. The script stops if the *estimated*
destination database table sizes reach 3000 MiB. This metadata guard is
not a reliable substitute for checking physical storage in Railway. The
Railway MySQL service is currently on a 5-GB volume.

Do not run simultaneous importers against the same job. Existing test
rows are preserved via duplicate-key handling. Source image, price,
category and vehicle compatibility data remain outside this importer.

## OEM migration without modifying source indexes

On source `td1q2018.article_oe`, the current index only begins with
`supplierid, datasupplierarticlenumber`; therefore `full_import.py --job oem`
intentionally stops at preflight. Do NOT add a compound index to the 50-GiB
source merely to make that command pass.

Use `oem_indexed_import.py` instead. It iterates source article IDs in indexed
order and retrieves all OEM rows for each article using the existing pair index.
Its checkpoint is atomic with the Railway target writes in
`catalogue_import_progress`, under the job `oem-by-article`.
One unit of progress is an *article examined*, not an OEM row; a batch may
contain zero or many OEM rows. This is a correctness-first migration path,
possibly slow at millions of indexed lookups.

```powershell
cd "C:\CarPot\Catalogue"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/TsPa33/telegram-bot/feature/carpot-catalogue-mvp/catalogue/oem_indexed_import.py" -OutFile "oem_indexed_import.py"
python -u .\oem_indexed_import.py --preflight --confirm-staging
python -u .\oem_indexed_import.py --max-articles 100 --batch-articles 25 --confirm-staging
```

After verifying the results in HeidiSQL, subsequent runs may increase
`--max-articles` up to 20,000 (per-run cap) without discarding checkpoints.
This only imports OEM records attached to source article keys existing in
`articles`; orphan OEM rows, if any, require a separate integrity audit.

No source modifications; no warehouse migrations; stop if the Railway disk
is near capacity (the metadata guard is an approximation).
