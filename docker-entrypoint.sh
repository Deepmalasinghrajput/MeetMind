#!/bin/sh
set -e

# Render (and many PaaS) inject $PORT — default local Docker uses 5000
PORT="${PORT:-5000}"
WORKERS="${WEB_CONCURRENCY:-1}"
TIMEOUT="${GUNICORN_TIMEOUT:-600}"
THREADS="${GUNICORN_THREADS:-1}"

echo "Starting AI Meeting Assistant on 0.0.0.0:${PORT} (workers=${WORKERS}, threads=${THREADS}, timeout=${TIMEOUT}s)"

# Preload Whisper in a light way is too heavy at boot; keep a single worker/thread
# so Render memory stays under control during transcription.
exec gunicorn \
  --workers="${WORKERS}" \
  --threads="${THREADS}" \
  --timeout="${TIMEOUT}" \
  --bind="0.0.0.0:${PORT}" \
  --access-logfile=- \
  --error-logfile=- \
  "app:app"
