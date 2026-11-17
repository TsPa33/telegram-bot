#!/bin/sh
# Invoked exactly once by the official Postgres entrypoint on a fresh PGDATA.
set -eu
: "${PREVIEW_APP_PASSWORD:?}" "${PREVIEW_OWNER_HASH:?}" "${PREVIEW_OWNER_CIPHER:?}"
[ "$POSTGRES_DB" = "carpot_control_preview" ] || exit 1
psql -X -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv app_password PREVIEW_APP_PASSWORD
CREATE ROLE cc_preview_migrator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE cc_preview_operator NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
CREATE ROLE cc_preview_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD :'app_password';
REVOKE ALL ON DATABASE carpot_control_preview FROM PUBLIC;
GRANT CONNECT ON DATABASE carpot_control_preview TO cc_preview_app;
GRANT CREATE ON DATABASE carpot_control_preview TO cc_preview_migrator;
SET ROLE cc_preview_migrator;
\i /opt/control/001.sql
INSERT INTO control_center.schema_version VALUES ('001','staging');
\set app_role cc_preview_app
\set operator_role cc_preview_operator
\i /opt/control/grants.sql
\i /opt/control/seed.sql
RESET ROLE;
SQL
