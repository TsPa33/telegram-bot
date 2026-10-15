#!/bin/sh
set -eu
: "${PORT:=8080}"
: "${WAREHOUSE_PUBLIC_ORIGIN:?Set the exact public https origin, without a trailing slash}"
: "${WAREHOUSE_BACKEND_ORIGIN:?Set the private backend origin, including its port}"
case "$PORT" in ''|*[!0-9]*) echo 'PORT must be numeric' >&2; exit 1;; esac
[ "$PORT" -ge 1024 ] && [ "$PORT" -le 65535 ] || { echo 'PORT must be 1024..65535' >&2; exit 1; }
printf '%s' "$WAREHOUSE_PUBLIC_ORIGIN" | grep -Eq '^https://[a-z0-9][a-z0-9.-]*(:[0-9]{1,5})?$' || { echo 'WAREHOUSE_PUBLIC_ORIGIN must be an exact lowercase HTTPS origin' >&2; exit 1; }
printf '%s' "$WAREHOUSE_BACKEND_ORIGIN" | grep -Eq '^http://[a-zA-Z0-9][a-zA-Z0-9.-]*:[0-9]{1,5}$' || { echo 'WAREHOUSE_BACKEND_ORIGIN must be http://private-host:port' >&2; exit 1; }
public_authority=${WAREHOUSE_PUBLIC_ORIGIN#https://}
WAREHOUSE_PUBLIC_HOST=${public_authority%%:*}
WAREHOUSE_PUBLIC_PORT=443
case "$public_authority" in *:*) WAREHOUSE_PUBLIC_PORT=${public_authority##*:};; esac
# Runtime DNS is essential: Railway internal DNS is unavailable during builds and
# backend addresses can change on redeploy. Support both A and AAAA records.
WAREHOUSE_DNS_RESOLVERS=$(awk '$1 == "nameserver" { if (index($2, ":")) printf "[%s] ", $2; else printf "%s ", $2 }' /etc/resolv.conf)
[ -n "$WAREHOUSE_DNS_RESOLVERS" ] || { echo 'No runtime DNS resolver configured' >&2; exit 1; }
export PORT WAREHOUSE_PUBLIC_HOST WAREHOUSE_PUBLIC_PORT WAREHOUSE_BACKEND_ORIGIN WAREHOUSE_DNS_RESOLVERS
# Substitute only known configuration names; preserve Nginx's $host/$uri/etc.
envsubst '${PORT} ${WAREHOUSE_PUBLIC_HOST} ${WAREHOUSE_PUBLIC_PORT} ${WAREHOUSE_BACKEND_ORIGIN} ${WAREHOUSE_DNS_RESOLVERS}' \
    < /etc/nginx/warehouse-server.conf.template > /tmp/warehouse-server.conf
nginx -t
exec nginx -g 'daemon off;'
