# CLAUDE.md

## Project

Personal FastAPI dashboard at `webapp/app.py`, served by gunicorn on `127.0.0.1:8000`. Templates in `webapp/templates/`. Auth is session-cookie based.

**Adding a new app:** backend routes in `app.py`, new template in `webapp/templates/`, entry in `templates/index.html` and `templates/base.html` nav. Reload: `kill -HUP <gunicorn master PID>`. Commit/push via Gittyup (`POST /gittyup/commit` with session cookie, or the `/gittyup` UI).

## Session Logging

Write a session log to `Memory/` and commit it via Gittyup when:
- A meaningful piece of work is complete (app built, feature added, significant decision made), or
- The user says "log this" or "we're done"

There is no automatic end-of-conversation trigger, so log at natural completion points rather than waiting for a signal that won't come.

**Format:** Create or append to a relevant file in `Memory/` (e.g. `Memory/actoroverlap.md`, `Memory/hpl-p1.md`). Each entry should include:
- Date
- What was built or discussed
- Decisions made and why
- Open questions or next steps
- Anything non-obvious that future-me should know

If a topic doesn't have a file yet, create one. If it does, append a new dated section. Commit via Gittyup with a message like "Memory: log YYYY-MM-DD session".
