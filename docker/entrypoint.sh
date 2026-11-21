#!/bin/sh
# Shelfpass container entrypoint.
#   web      migrate, sync the dataset, then serve with gunicorn (default)
#   manage   run any manage.py command, e.g. `docker run … manage createsuperuser`
#   anything else is executed as-is.
set -eu

prepare() {
  if [ "${SHELFPASS_MIGRATE:-1}" = "1" ]; then
    python /app/manage.py migrate --noinput
  fi
  if [ "${SHELFPASS_SYNC_DATASET:-1}" = "1" ]; then
    python /app/manage.py sync_dataset
  fi
  if [ "${SHELFPASS_DEMO:-0}" = "1" ]; then
    python /app/manage.py seed_demo --force || echo "Demo data already present; skipping."
  fi
}

case "${1:-web}" in
  web)
    prepare
    exec gunicorn shelfpass.wsgi:application \
      --bind "0.0.0.0:${PORT:-8000}" \
      --workers "${WEB_CONCURRENCY:-3}" \
      --timeout "${GUNICORN_TIMEOUT:-60}" \
      --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}" \
      --access-logfile - \
      --error-logfile -
    ;;
  manage)
    shift
    exec python /app/manage.py "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
