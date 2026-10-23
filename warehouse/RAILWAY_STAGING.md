> Current update policy: keep Warehouse Auto Deploy ON and publish backend and
> frontend in separate GitHub pushes. Follow [STAGED_AUTO_DEPLOY.md](STAGED_AUTO_DEPLOY.md).
> The existing `warehouse-staging` and `postgres` are reused: do not create a new
> environment/database, reset POSTGRES_* variables, or replace its volume. The
> initial-install sections below apply only when those resources do not yet exist.

# Railway staging preview — Warehouse only

This guide prepares a **new EMPTY environment named `warehouse-staging` inside your EXISTING paid Railway project** for visual testing on iPhone and desktop. Keep your current subscription and project. Nothing in this change deploys to Railway, connects to a Railway account, changes production CarPot, or reads its variables, databases, credentials or volumes.

Create the environment with Railway's **Empty Environment** option. Never duplicate, clone, fork or sync production. Create only `postgres`, `warehouse-api` and `warehouse-web` in `warehouse-staging`. No production service instance is required in this environment.

For the current Plan.Parts integration, also follow [PLAN_PARTS_STAGING.md](PLAN_PARTS_STAGING.md): keep `PLAN_PARTS_ENABLED=false` for the first deployment, distinguish a fresh database from an existing Warehouse upgrade, verify revision `c91e72b6a410`, and use the documented backup/recovery procedure. The new integration and this revised guide must be reviewed and published on the feature branch before Railway can build them.

## Topology

```text
https://<generated-warehouse-web-domain>.up.railway.app
          Railway TLS edge (HTTPS)
                       |
             warehouse-web :8080
        production Vite dist served by Nginx
                       |
           /api/* and /health, private HTTP
                       |
             warehouse-api :8010
          FastAPI, startup migrations
                       |
              private PostgreSQL
                       |
             postgres :5432
          volume /var/lib/postgresql/data
```

Only `warehouse-web` gets a public domain. **Neither API nor PostgreSQL gets a public domain, TCP proxy, or Public Access.** All three services must be in the **existing project**, the **`warehouse-staging` environment only**, and the same region. Railway private networks are isolated by environment, so services in `warehouse-staging` use that environment’s private DNS/network rather than production’s. This does not isolate billing or project/workspace administration. Private Railway traffic is carried by Railway's WireGuard network; internal URLs deliberately use `http://`, while the browser uses HTTPS only.

Both application services build from repository **`TsPa33/telegram-bot`**, branch **`feature/carpot-warehouse-mvp`**, Root Directory **`/warehouse`**. Root CarPot startup files, `render.yaml`, and dependency manifests are not build inputs. The local development Dockerfiles and Compose stay development-only; staging uses `deploy/railway/*.Dockerfile`.

`deploy/railway/services.json` is a **reviewable Dashboard settings checklist**, not a Railway-importable schema or executable deployment script. Its values are reproduced below. Do not import the local check Compose file into Railway.

Current Railway documentation deprecates `railway.json`/`railway.toml` for new services in favor of IaC. This preparation uses supported Dashboard service settings and `RAILWAY_DOCKERFILE_PATH`; it does not introduce legacy configuration or apply a project-wide IaC graph to an existing project.

## 1. Make the feature branch available (when you choose to deploy)

The Warehouse MVP and original staging preparation were pushed to `feature/carpot-warehouse-mvp` at commit `6e8f4d7a73cd9c2a94f79f81ca86cd5f5919042c`. Review and commit/push this revised plan if it has not yet been published; do not repeat a commit when the worktree is already clean:

```bash
git switch feature/carpot-warehouse-mvp
git status --short
git add warehouse
git diff --cached --stat
git commit -m "feat(warehouse): integrate Plan.Parts vehicle lookup"
git push -u origin feature/carpot-warehouse-mvp
```

No merge into `main` is needed. `.env`, local TLS test keys, photos, and dependency/build caches are ignored. Do not stage credentials. GitHub access for the Railway GitHub App must include this repository; no CarPot production token is needed.

## 2. Create an EMPTY environment in the existing project and its private database

1. Open your **existing paid Railway project** without changing its production configuration. In the environment selector choose **New Environment → Empty Environment**, name it exactly **`warehouse-staging`**, and select it. Do not choose Duplicate Environment and do not use Sync/Import from production in either direction.
2. Confirm the environment selector reads `warehouse-staging` and its canvas contains **zero services**. If CarPot services appear, stop and verify the selected environment and creation mode; do not delete, move, pause or redeploy those services to "clean it up".
3. Add an **empty service in `warehouse-staging` only**, name it exactly `postgres`, and select Docker image **`postgres:16-alpine`**. Keep its deployment staged/paused until its variables and volume are configured. Do not use a project/environment duplication template.
4. Attach a **new independent Railway Volume** at `/var/lib/postgresql/data` to this new database instance. Do not reuse, restore, clone or connect a production volume/database. Set the smallest supported size with adequate PostgreSQL/WAL headroom for your expected staging data; the smallest useful size depends on Railway's current volume controls.
5. Set these variables **before its first database initialization**:

| Variable | Value |
|---|---|
| `POSTGRES_DB` | `warehouse_staging` |
| `POSTGRES_USER` | `warehouse_staging` |
| `POSTGRES_PASSWORD` | A new random secret, entered in Railway; never a CarPot password |
| `PGDATA` | `/var/lib/postgresql/data/pgdata` |

Use **service-local variables in `warehouse-staging`**. Do not modify production variables, project/workspace defaults, or existing shared variables. Do not bind `${{shared.*}}` values from CarPot. References below connect only the three Warehouse services within the selected environment. Leave production source branches, deployments, volumes, domains, limits and automation exactly as they are.

Generate a unique password locally with a password manager or `openssl rand -hex 32`; enter it only in the `postgres` service's Variables panel. Do not put the value in a commit, command argument, build argument, frontend variable, or chat.

Leave Start Command empty (use the official image's entrypoint). Use one replica. Leave HTTP healthcheck unset for PostgreSQL. Ensure **Networking has no Public Access/TCP proxy**. Deploy this service only after checking those settings.

**Important:** PostgreSQL's `POSTGRES_DB` only creates that database on an empty volume. Changing the variable later does not rename/create a database on an initialized volume. If first initialization used another name, use an explicit PostgreSQL administration operation over Railway's private console to create `warehouse_staging`; do not point the API at `railway` or another application's database to bypass Warehouse's name guard. Do not delete a volume containing work.

This deliberately uses a fresh official Postgres image rather than a template that might initialize its default database before you change the name. Enable volume backups if you intend to retain staging records between iterations. Never treat a staging volume as disposable after entering real test data.

## 3. Create the two application services before releasing their builds

While the selector still reads **`warehouse-staging`**, create two **empty** services named exactly `warehouse-api` and `warehouse-web`. The final canvas must contain exactly these two services plus `postgres`, with no CarPot service instances. Connect each to the feature branch with the settings below. Keep initial source/deployment changes staged or deployments paused until the Root Directory, branch, custom Dockerfile path, and variables are set. Do not accept a repository-root auto-detected bot start command.

If your UI connects GitHub before showing Root Directory, leave deployments paused while configuring the service. Review the final deployment details to verify `/warehouse` and the expected Dockerfile before deploying it.

| Setting | `warehouse-api` | `warehouse-web` |
|---|---|---|
| Source repo | `TsPa33/telegram-bot` | `TsPa33/telegram-bot` |
| Branch | `feature/carpot-warehouse-mvp` | `feature/carpot-warehouse-mvp` |
| Root Directory | `/warehouse` | `/warehouse` |
| Builder | Dockerfile | Dockerfile |
| `RAILWAY_DOCKERFILE_PATH` | `deploy/railway/backend.Dockerfile` | `deploy/railway/frontend.Dockerfile` |
| Start Command | `python -m app.staging` | `/usr/local/bin/warehouse-frontend` |
| `PORT` | `8010` | `8080` |
| Healthcheck | `/health` | `/health` |
| Healthcheck timeout | 180 seconds | 180 seconds |
| Replicas | 1 | 1 |
| Restart policy | On failure, max 5 retries | On failure, max 5 retries |
| Public networking | **None** | One generated HTTPS domain, target port `8080` |
| Volumes | None initially; optional photo volume below | None |

Leaving Start Command empty also uses the same Docker CMD/ENTRYPOINT. Do not set a separate Build Command or Vite development/preview command. The frontend image runs `npm ci` + `npm run build`, then copies only `dist` to an Nginx runtime with no Node or Vite server.

Generate a domain **only for `warehouse-web`**, targeting port `8080`. Reserve it before the API's first startup if the UI allows it, so both services can have the same exact public-origin setting. No custom CarPot DNS changes are needed.

If your Railway UI offers domain generation only after a first deployment, temporarily set **both** application origins to `https://warehouse-bootstrap.invalid`. Deploy API then web with that exact placeholder; their Railway `/health` checks accept `healthcheck.railway.app`, but requests on an unconfigured public hostname are rejected. Generate the web domain, replace both origins with the real reference expressions below, and redeploy API then web **before creating an account or testing login**. Never disable secure cookies or host/origin checks to bootstrap a domain.

### Frontend variables

Use Railway variable reference expressions exactly as shown, with the service names above:

| Variable | Value |
|---|---|
| `PORT` | `8080` |
| `RAILWAY_DOCKERFILE_PATH` | `deploy/railway/frontend.Dockerfile` |
| `WAREHOUSE_PUBLIC_ORIGIN` | `https://${{RAILWAY_PUBLIC_DOMAIN}}` |
| `WAREHOUSE_BACKEND_ORIGIN` | `http://${{warehouse-api.RAILWAY_PRIVATE_DOMAIN}}:8010` |

`RAILWAY_PUBLIC_DOMAIN` must be present after generating the domain. Use the canonical **full HTTPS origin without a trailing slash**. If you later choose a custom staging domain, set that exact origin in both services instead of the generated-domain expressions. Use a domain dedicated to Warehouse staging, not the main CarPot domain.

Swagger `/docs` and `/openapi.json` remain on the private backend; they are not publicly proxied.

No `VITE_API_URL` or CORS configuration is needed: browser fetches remain relative `/api/v1/...`. Do not set `WAREHOUSE_API_PROXY` in staging; that variable is only used by the local Vite dev server. The Nginx upstream is runtime-configured, resolves both A/AAAA records, and refreshes DNS after backend redeploys.

### Backend variables

The Railway environment name is **`warehouse-staging`**. The application’s mode flag remains **`WAREHOUSE_ENV=staging`** because the staging entrypoint validates that literal value. Do not rename the mode flag to match the Railway selector, and do not override Railway's own environment metadata variables.

| Variable | Value |
|---|---|
| `PORT` | `8010` |
| `RAILWAY_DOCKERFILE_PATH` | `deploy/railway/backend.Dockerfile` |
| `WAREHOUSE_ENV` | `staging` |
| `WAREHOUSE_COOKIE_SECURE` | `true` |
| `WAREHOUSE_REGISTRATION_ENABLED` | `false` |
| `WAREHOUSE_PUBLIC_ORIGIN` | `https://${{warehouse-web.RAILWAY_PUBLIC_DOMAIN}}` |
| `WAREHOUSE_DB_HOST` | `${{postgres.RAILWAY_PRIVATE_DOMAIN}}` |
| `WAREHOUSE_DB_PORT` | `5432` |
| `WAREHOUSE_DB_NAME` | `${{postgres.POSTGRES_DB}}` |
| `WAREHOUSE_DB_USER` | `${{postgres.POSTGRES_USER}}` |
| `WAREHOUSE_DB_PASSWORD` | `${{postgres.POSTGRES_PASSWORD}}` |
| `WAREHOUSE_STARTUP_TIMEOUT` | `120` |
| `WAREHOUSE_FORWARDED_ALLOW_IPS` | `fd00::/8,10.0.0.0/8` |

Do not also set `WAREHOUSE_DATABASE_URL`: it takes precedence over component variables and could silently target the wrong database. Never bind the existing CarPot `DATABASE_URL`. Component variables construct a properly escaped SQLAlchemy URL, including passwords with reserved characters.

Private proxy trust is restricted to the Railway private ranges above; do not replace it with `*`. Backend sockets support IPv4 and IPv6. If Railway assigns a different private range to your environment, confirm the **frontend private source range** and set that narrower range explicitly. Backend must remain private. Nginx overwrites X-Forwarded-* from Railway's documented `X-Real-IP`, canonical HTTPS scheme, and request host rather than trusting a caller-supplied XFF chain. This assumes frontend public requests enter through Railway's TLS edge; only the three Warehouse services in this environment are trusted infrastructure. Other environments in the project have separate private networks; no production service is an upstream or credential source.

### Optional persistent photos

Initial staging can leave `WAREHOUSE_PHOTO_DIR` unset; the UI then honestly shows that photos are unavailable. Do **not** enable a path on ephemeral container storage.

To test photos across redeploys:

1. Add a dedicated API volume mounted at **`/data/photos`**.
2. Set `WAREHOUSE_PHOTO_DIR=/data/photos` and `RAILWAY_RUN_UID=0` on **warehouse-api only**.
3. The staging entrypoint changes only that mount root's ownership, then drops supplementary groups, gid and uid to the `warehouse` user (uid 1000) **before migrations and HTTP serving**. It never recursively chowns files or runs the API as root.
4. Confirm a real photo persists after an API redeploy. Back up the volume if records matter.

Railway mounts volumes as root. Omitting the bootstrap on a root-owned volume fails startup with a writable-directory error; do not work around this by leaving the running server privileged. Attached volumes can cause a short redeploy interruption because Railway does not mount the same volume on overlapping deployments. Database storage remains independent of the optional photo volume.

## 4. Deploy and create YOUR account

When you decide to deploy:

1. Deploy `postgres`; confirm initialization succeeds and the volume is attached.
2. Confirm the frontend domain is reserved and both origin reference expressions resolve to the same domain.
3. Deploy `warehouse-api`. Its startup validates configuration, drops bootstrap privileges if needed, waits for the private DB, takes a PostgreSQL advisory lock, runs `alembic upgrade head`, then serves HTTP. Do not add migrations to the Docker build or run a second unguarded migration command.
4. Confirm API health and the message `Warehouse migrations complete`. It is still private.
5. Deploy `warehouse-web`; its healthcheck traverses Nginx → API → DB and verifies the migration head. Only a healthy chain receives traffic.
6. Create your **real** owner account using an interactive backend shell: select **your existing project**, environment **warehouse-staging**, service **warehouse-api**, then run `python -m app.create_owner`. With Railway CLI, use `railway link` to select those exact targets and `railway ssh --service warehouse-api` to open the shell. The command prompts for your real name/email and a non-echoed password twice; no inventory is created. It will not reset an existing account's password.
7. Open the frontend HTTPS domain on iPhone and desktop, sign in, and enter only your own test records. Registration remains closed on the public staging URL.

Do not use `railway run` to access the private DB from your laptop; it injects variables but does not put the laptop on Railway's private network. Do not expose PostgreSQL to make account creation work. Use the interactive shell in the API container. If CLI/project permissions do not allow that shell, stop at that prerequisite; an alternative is to deliberately enable registration briefly, register yourself through HTTPS, then disable it and redeploy the API. Do not ship a hardcoded/bootstrap password.

## 5. Check the live preview after deployment (not yet performed)

Expected URL pattern:

```text
https://<warehouse-web-service-slug>-<railway-generated-suffix>.up.railway.app
```

Railway chooses the exact generated hostname. The guide does not claim a domain has been created. Keep the same frontend service/domain across updates so sessions and bookmarks remain useful.

Check on desktop and real iPhone Safari:

- `/health` returns 200; an unauthenticated `/api/v1/auth/me` returns JSON 401, not SPA HTML.
- Login, refresh, deep-link to `/inventory`, add a real donor, add a real part, receive/reserve/release stock, inspect audit, then logout.
- Browser cookies show `warehouse_session`: **Secure, HttpOnly, SameSite=Strict, Path=/api/v1**, host-only; `warehouse_csrf`: **Secure, SameSite=Strict, Path=/**, readable by the same-origin client for `X-CSRF-Token`.
- Mutations include the exact HTTPS `Origin` and CSRF token. Cross-origin or token-less mutations fail with 403. Do not add CORS wildcards or change SameSite to None.
- No database host/credentials appear in frontend assets, page source, or browser request URLs. All API requests use the frontend domain.
- After API redeploy, records and a still-valid login session survive; after logout, that session is revoked. A replaced API's IP is rediscovered at runtime by Nginx.

The frontend sets HSTS, CSP, frame denial, nosniff, and noindex headers, and blocks indexing in `robots.txt`. CSP allows inline **styles** for React's chart widths, not inline scripts. Search-engine directives do not authenticate a site: login remains required for data, registration is closed, and the public login page is intentionally reachable. An additional Railway access gate is optional but would need separate testing with mobile sessions and healthchecks.

## 6. Update after each iteration without touching CarPot

Keep Auto Deploy **ON** for the two Warehouse application services on the **feature branch only**. Publish backend first, wait for the authenticated Dismantling readiness gate, then publish frontend in a separate push. See STAGED_AUTO_DEPLOY.md; do not use Railway CLI or a manual Deploy/Redeploy action. Leave every production autodeploy/PR-environment setting unchanged. Configure these Watch Paths (repository-relative, even with Root Directory set):

- API: `/warehouse/backend/**`, `/warehouse/deploy/railway/backend.Dockerfile`, `/warehouse/.dockerignore`.
- Web: `/warehouse/frontend/**`, `/warehouse/deploy/railway/frontend.Dockerfile`, `/warehouse/deploy/railway/frontend-start.sh`, `/warehouse/deploy/railway/nginx/**`, `/warehouse/.dockerignore`.

Use separate backend and frontend commits AND separate pushes, with the readiness gate between them. Pushing two commits together does not serialize Railway deployments. Shared .dockerignore changes trigger both services and require separate coordination. Existing CarPot remains on its existing configuration/branch; do not change it.

Migrations must be backward-compatible while an older API instance may serve requests during a rollout. Use additive expand/contract changes. The startup lock prevents two migration processes from running at once; it cannot make destructive migrations compatible with old code. Back up staging before destructive changes. Never automatically downgrade or reseed the DB on restart or rollback. Rolling the image back does not roll the database back.

Use one replica/one worker: the current auth throttle is per process, while sessions are persisted in PostgreSQL. A distributed limiter is needed before scaling. Railway deployment healthchecks gate releases; they are not continuous uptime monitoring. Optional photo volumes can introduce a short restart pause.

## 7. Cost-efficient visual testing and billing

This adds **an environment under the existing subscription/project**, not another purchased subscription or project. Whether your current tier permits the additional environment/services/volume must be confirmed in that existing workspace's limits; this guide does not assume an upgrade or change your plan. Production and Warehouse consumption draw from the **same billing allowance/credits and spending limits**. Environment isolation does not make the new services free or create separate included credits.

Recommended initial profile:

| Resource | Cost-conscious setting | Operational effect |
|---|---|---|
| `warehouse-web` | 1 Nginx replica, production static assets, generated Railway HTTPS domain | No Vite dev server, Node runtime, separate CDN, or purchased custom domain |
| `warehouse-api` | 1 replica, 1 worker (already configured) | Avoids replica multiplication; retains the current single-process auth-throttle model |
| `postgres` | 1 private PostgreSQL instance, independent persistent volume | Small starting dataset; no public TCP proxy, replica, pooler, or production DB sharing |
| Photos | Disabled initially; no API volume | Avoids a second storage volume until photo testing is actually needed |
| Extra services | None | No Redis, preview-per-PR environments, staging bot, monitoring service, or scheduler |
| App updates | Manual Warehouse-only deploys by default; optional feature-branch watch paths | Lets the stack remain offline between testing sessions; never alters production automation |
| Replica limits | Apply only to Warehouse service instances after measuring startup and normal testing peaks | Limits are ceilings, not reservations or a price quote; overly small RAM limits cause crashes |

For a stable iPhone demo window, keep all three Warehouse services awake for the duration of that window. For the lowest idle compute cost, **stop all three Warehouse deployments outside testing hours while retaining their service configuration, database volume and domain**:

1. Verify `warehouse-staging` and the selected service name before every operation. Stop/remove only the active **deployment instance** of `warehouse-web`, then `warehouse-api`, then `postgres`. In Railway UIs where the action is called **Remove**, it means the deployment, not Delete Service or Delete Volume. Allow graceful shutdown; `RAILWAY_DEPLOYMENT_DRAINING_SECONDS=30` is recommended on these three Warehouse instances only.
2. Verify the three Warehouse deployment instances are no longer active. Do not delete services, the environment, the database volume or its data. Pausing GitHub deployments by itself does not stop already-running containers and does not eliminate their compute usage.
3. Before the next session, start/redeploy the existing DB instance **with its retained volume**, then API, then web. Wait for `/health`, then open the same HTTPS URL on your iPhone. Migrations rerun safely; existing records/accounts remain. The preview is deliberately unavailable while stopped.

If always-available convenience is more important than the minimum bill, keep the small stack running and measure its usage. Railway Serverless/App Sleeping may be tried **only on Warehouse instances**, but it is an optional experiment, not the default or a guaranteed saving: API connection pools and private traffic can prevent sleep; cold starts can produce a temporary 502. Current Nginx connection/read timeouts and readiness must be tested with the actual sleeping backend. Do not rely on sleeping PostgreSQL for a stable preview, add an always-on pinger, or change production's sleep settings.

### What may add to the bill

- **RAM and CPU:** all running Warehouse containers consume metered resources, including idle PostgreSQL memory. A resource limit is not the amount necessarily billed; measured use and running time matter.
- **Persistent storage:** the new DB volume remains billable while compute is stopped. Optional photo storage and backup retention can add storage usage; check the applicable plan's charging rules. Stopping containers does not erase or make retained data free.
- **Network:** frontend responses, JS/CSS bundles and downloaded photos create public egress. Keeping API/DB traffic on the environment's private network avoids unnecessary public egress.
- **Other account usage:** production may already consume the included allowance. Warehouse overages are charged under the same account/workspace; there is no separate free budget just because the environment is new.

Use Railway's displayed rates and usage metrics for the actual bill. As a **planning illustration, not a measurement or quote**, at the documented container RAM rate of **$10/GB-month**, a stack averaging **0.5 GB total RAM** costs about **$5/month for RAM alone** if always running, or about **$0.83/month** for RAM alone at 4 hours/day with all compute stopped the rest of the time. Add actual CPU, retained storage, egress, and any other applicable charges; subtract only the included allowance that remains unused. These averages have **not** been measured for this Warehouse deployment. Other reference rates in the consulted docs are $20/vCPU-month, $0.15/GB-month volume storage and $0.05/GB public egress; current workspace pricing is authoritative.

Inspect read-only usage/metrics filtered to `warehouse-staging` and its three service instances after a representative session. Do not lower or replace a **workspace/account-wide hard spending limit** as if it applied only to staging: reaching it may take production workloads offline. This task makes no billing, plan, production resource-limit or shared-variable changes. Stop Warehouse compute rather than reducing production capacity to fit a staging budget.

## Local checks included with this preparation

No Railway credentials are needed for these commands. They only create disposable local containers under a separate project name; they do not publish ports for PostgreSQL or call Railway.

```bash
cd warehouse
python3 deploy/railway/check-config.py
docker build -f deploy/railway/backend.Dockerfile -t carpot-warehouse-staging-backend .
docker build -f deploy/railway/frontend.Dockerfile -t carpot-warehouse-staging-frontend .
# If this cloud needs its existing trusted proxy/CA:
# python3 scripts/build-cloud-images.py staging-backend
# python3 scripts/build-cloud-images.py staging-frontend
# Use an installed Chromium or install Playwright's supported Chromium first.
WAREHOUSE_CHROMIUM_PATH=/usr/bin/chromium python3 deploy/railway/check-run.py
```

`check-run.py` runs the backend suite in the staging image, checks actual local HTTPS with a trusted test CA, secure cookies, CSRF/origin rejection, production asset/deep-link routing, closed signup, non-root serving, DB/session preservation on API replacement, and failure of frontend health when the API is down. Desktop and iPhone-sized Chromium workflows exercise production Nginx without Vite. Browser verification pins only the generated local test certificate's public key; it does not disable general TLS validation. These are responsive Chromium checks, **not a claim that physical iPhone Safari or Railway has been tested**.

Synthetic fixtures are created only in `warehouse_staging_test` in the disposable local project. The runner removes that project's containers/volume and its temporary credentials/TLS keys at the end. Do not run a destructive test suite against the real `warehouse_staging` database. Local check screenshots live in ignored `deploy/railway/.check/`.

## What is still external

The code/images/configuration can be verified locally. Actual Railway build admission, GitHub App permission, empty-environment creation in the existing project, volume provisioning, domain/TLS issuance, region-specific proxy ranges, private-network routing and iPhone Safari behavior must be confirmed after **you choose to deploy**. Publish this revised plan to the feature branch before following it; the original MVP/preparation has already been pushed. No environment, services, volume or live preview URL have been created by this revision; no existing CarPot service, production database, domain, or credentials has been accessed or changed.

Official Railway references consulted: [Dockerfiles](https://docs.railway.com/builds/dockerfiles), [monorepo roots/watch paths](https://docs.railway.com/deployments/monorepo), [private networking](https://docs.railway.com/networking/private-networking/how-it-works), [edge headers/TLS](https://docs.railway.com/networking/public-networking/specs-and-limits), [healthchecks](https://docs.railway.com/deployments/healthchecks), [volumes](https://docs.railway.com/volumes), [current IaC status](https://docs.railway.com/infrastructure-as-code). The documentation was read from the official `railwayapp/docs` GitHub repository because the documentation website was unavailable from this cloud network.

For the environment-isolation and billing details, also see [Environments](https://docs.railway.com/environments), [private-network boundaries](https://docs.railway.com/networking/private-networking/how-it-works), [resource pricing](https://docs.railway.com/pricing/plans), [cost controls](https://docs.railway.com/pricing/cost-control), and [Serverless caveats](https://docs.railway.com/deployments/serverless). These public references do not establish your particular subscription's remaining allowance or quotas.

Executed checks and the exact file list: [deploy/railway/VALIDATION.md](deploy/railway/VALIDATION.md).
