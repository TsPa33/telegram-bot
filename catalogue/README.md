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
