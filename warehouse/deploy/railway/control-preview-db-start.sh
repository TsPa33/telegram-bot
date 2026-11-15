#!/bin/sh
set -eu
# The image must only be used with a new isolated preview DB.
: "${POSTGRES_DB:?}" "${POSTGRES_PASSWORD:?}" "${PREVIEW_DB_CERT:?}" "${PREVIEW_DB_KEY:?}"
[ "$POSTGRES_DB" = "carpot_control_preview" ] || exit 1
umask 077
mkdir -p /tmp/control-tls
printf '%s\n' "$PREVIEW_DB_CERT" > /tmp/control-tls/server.crt
printf '%s\n' "$PREVIEW_DB_KEY" > /tmp/control-tls/server.key
chown -R postgres:postgres /tmp/control-tls
chmod 600 /tmp/control-tls/server.key
exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/tmp/control-tls/server.crt -c ssl_key_file=/tmp/control-tls/server.key -c password_encryption=scram-sha-256 -c listen_addresses='*'
