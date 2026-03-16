#!/usr/bin/env bash
# Run the dashboard web server
cd "$(dirname "$0")"
# Load .env if present
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
exec venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --reload
