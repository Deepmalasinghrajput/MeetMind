#!/bin/sh
set -e

# Render (and many PaaS) inject $PORT — default local Docker uses 5000
PORT="${PORT:-5000}"
WORKERS="${WEB_CONCURRENCY:-1}"
TIMEOUT="${GUNICORN_TIMEOUT:-600}"
THREADS="${GUNICORN_THREADS:-2}"

echo "Starting MeetMind on 0.0.0.0:${PORT} (workers=${WORKERS}, timeout=${TIMEOUT}s)"

exec gunicorn \
  --workers="${WORKERS}" \
  --threads="${THREADS}" \
  --timeout="${TIMEOUT}" \
  --bind="0.0.0.0:${PORT}" \
  --access-logfile=- \
  --error-logfile=- \
  "app:app"
