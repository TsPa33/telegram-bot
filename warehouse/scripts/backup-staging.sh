#!/bin/sh
# One explicit read-only dump. Never invoked by the API or migration startup.
set +x
set -eu
umask 077

fail() { printf '%s\n' "$1" >&2; exit 1; }
mode=${1:-}
case "$mode" in
  --confirm-warehouse-staging)
    [ "${RAILWAY_ENVIRONMENT_NAME:-}" = warehouse-staging ] || fail 'Refusing backup outside warehouse-staging.'
    case "${WAREHOUSE_DB_HOST:-}" in ''|*[!A-Za-z0-9.-]*) fail 'A single private Railway hostname is required.';; esac
    case "$WAREHOUSE_DB_HOST" in [A-Za-z0-9]*.railway.internal) ;; *) fail 'A private Railway database hostname is required.';; esac
    ;;
  --local-test)
    [ -z "${RAILWAY_ENVIRONMENT_NAME:-}" ] && [ -z "${RAILWAY_PROJECT_ID:-}" ] || fail 'Local test mode is forbidden on Railway.'
    case "${WAREHOUSE_DB_HOST:-}" in 127.0.0.1|localhost|::1) ;; *) fail 'Local test requires loopback.';; esac
    case "${WAREHOUSE_DB_NAME:-}" in *_test) ;; *) fail 'Local test requires a *_test database.';; esac
    ;;
  *) fail 'Use --confirm-warehouse-staging or --local-test explicitly.';;
esac
[ "$#" -eq 1 ] || fail 'Unexpected arguments.'
case "${WAREHOUSE_DB_NAME:-}" in warehouse*|carpot_warehouse*) ;; *) fail 'A Warehouse-specific database is required.';; esac
[ -n "${WAREHOUSE_DB_USER:-}" ] && [ -n "${WAREHOUSE_DB_PASSWORD:-}" ] || fail 'Warehouse DB credentials are missing.'
for identifier in "$WAREHOUSE_DB_NAME" "$WAREHOUSE_DB_USER"; do
  case "$identifier" in ''|*[!A-Za-z0-9_-]*) fail 'Unsupported database identifier.';; esac
done
[ -z "${WAREHOUSE_DATABASE_URL:-}" ] || fail 'Remove the ambiguous WAREHOUSE_DATABASE_URL override from this process.'
port=${WAREHOUSE_DB_PORT:-5432}
case "$port" in ''|*[!0-9]*) fail 'Invalid database port.';; esac
[ "$port" -ge 1 ] && [ "$port" -le 65535 ] || fail 'Invalid database port.'

for tool in pg_dump pg_restore psql mktemp sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || fail 'Required PostgreSQL 16 tools or system utilities are missing.'
done
for tool in pg_dump pg_restore psql; do
  major=$("$tool" --version | awk '{split($3,v,".");print v[1]}')
  [ "$major" = 16 ] || fail 'Use PostgreSQL 16 client tools for this PostgreSQL 16 staging backup.'
done

# Ignore libpq service/host-address overrides and force read-only connections.
unset PGSERVICE PGSERVICEFILE PGPASSFILE PGHOSTADDR
export PGHOST="$WAREHOUSE_DB_HOST" PGPORT="$port" PGDATABASE="$WAREHOUSE_DB_NAME"
export PGUSER="$WAREHOUSE_DB_USER" PGPASSWORD="$WAREHOUSE_DB_PASSWORD"
export PGCONNECT_TIMEOUT=10 PGAPPNAME=warehouse-staging-backup
export PGOPTIONS='-c default_transaction_read_only=on'
# Private WireGuard network; preserve any existing stricter libpq TLS setting.
export PGSSLMODE=${PGSSLMODE:-prefer}

directory=$(mktemp -d /tmp/warehouse-backup.XXXXXXXX) || fail 'Cannot create private temporary directory.'
complete=false
cleanup() {
  code=$?
  if [ "$complete" != true ]; then rm -rf -- "$directory"; fi
  exit "$code"
}
trap cleanup 0
trap 'exit 130' INT
trap 'exit 143' TERM HUP
archive="$directory/warehouse-staging.dump"
version=$(psql -X --no-password -At -c 'SHOW server_version_num' 2>/dev/null) || fail 'Database preflight failed; diagnostics suppressed.'
case "$version" in 16????) ;; *) fail 'Expected PostgreSQL 16 server.';; esac
revision_sql='SELECT version_num FROM public.alembic_version ORDER BY version_num'
psql -X --no-password -At -c "$revision_sql" >"$directory/source-revision.txt" 2>/dev/null || fail 'Warehouse Alembic revision is unavailable.'
[ -s "$directory/source-revision.txt" ] || fail 'Warehouse Alembic revision is empty.'
if [ "${WAREHOUSE_BACKUP_CHECK_ONLY:-false}" = true ]; then
  printf '%s\n' 'Preflight passed: warehouse-staging, private Warehouse DB, PostgreSQL 16, Alembic revision available. No pg_dump executed.'
  exit 0
fi

pg_dump --format=custom --no-owner --no-acl --no-password \
  --lock-wait-timeout=30s --file="$archive" 2>/dev/null || fail 'pg_dump failed; temporary files removed and diagnostics suppressed.'
pg_restore --list "$archive" >/dev/null 2>/dev/null || fail 'Backup table of contents is invalid.'
# Read/decompress ALL archive sections without executing their SQL.
pg_restore --no-owner --no-acl --file=/dev/null "$archive" 2>/dev/null || fail 'Backup payload validation failed.'
revision_after=$(psql -X --no-password -At -c "$revision_sql" 2>/dev/null) || fail 'Final revision check failed.'
[ "$(cat "$directory/source-revision.txt")" = "$revision_after" ] || fail 'Schema revision changed during backup; retry in a quiet window.'
(
  cd "$directory"
  sha256sum warehouse-staging.dump > warehouse-staging.dump.sha256
  sha256sum source-revision.txt > source-revision.txt.sha256
)
complete=true
printf 'Backup validated. Temporary directory: %s\n' "$directory"
printf '%s\n' 'Contains a private custom-format dump, SHA-256 sidecars and source Alembic revision.'
printf '%s\n' 'Retrieve using the verified non-terminal CLI transfer or an approved private TLS destination; remove the temporary directory after verified retrieval.'
