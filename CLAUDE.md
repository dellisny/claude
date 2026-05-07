# CLAUDE.md

## Project

Personal FastAPI dashboard at `webapp/app.py`, served by gunicorn on `127.0.0.1:8000`. Templates in `webapp/templates/`. Auth is session-cookie based.

**Adding a new app:** backend routes in `app.py`, new template in `webapp/templates/`, entry in `templates/index.html` and `templates/base.html` nav. Reload: `kill -HUP <gunicorn master PID>`. Commit/push via Gittyup (`POST /gittyup/commit` with session cookie, or the `/gittyup` UI).

## Session Logging

After every conversation, write a session log to `Memory/` and commit it via Gittyup. This applies to all work in this repo, not just specific projects.

**Format:** Create or append to a relevant file in `Memory/` (e.g. `Memory/actoroverlap.md`, `Memory/hpl-p1.md`). Each session entry should include:
- Date
- What was built or discussed
- Decisions made and why
- Open questions or next steps
- Anything non-obvious that future-me should know

If a topic doesn't have a file yet, create one. If it does, append a new dated section. After writing, commit via Gittyup with a message like "Memory: log YYYY-MM-DD session".
