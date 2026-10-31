#!/bin/sh
set -eu
# Railway volumes are mounted as root; grant access only to the photo mount.
# The API itself always runs as the unprivileged "warehouse" account.
if [ -n "${WAREHOUSE_PHOTO_DIR:-}" ]; then
  if [ "$WAREHOUSE_PHOTO_DIR" != "/data/photos" ]; then
    echo "WAREHOUSE_PHOTO_DIR must be /data/photos when photos are enabled" >&2
    exit 1
  fi
  mkdir -p /data/photos
  chown warehouse:warehouse /data/photos
  chmod 0750 /data/photos
fi
exec gosu warehouse "$@"
