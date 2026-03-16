#!/usr/bin/env bash
# Run the dashboard web server
cd "$(dirname "$0")"
# Load .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
exec venv/bin/gunicorn app:app \
  -k uvicorn.workers.UvicornWorker \
  -w 2 \
  --bind 0.0.0.0:8000 \
  --max-requests 500 \
  --max-requests-jitter 50
