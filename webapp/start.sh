#!/usr/bin/env bash
# Run the dashboard web server
cd "$(dirname "$0")"
exec venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
