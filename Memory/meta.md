# Meta — Session Log

## 2026-05-07 — Memory and tooling conventions established

### What was decided
- **Session logging:** After every conversation, Claude writes a dated entry to `Memory/` and commits via Gittyup. Covers all work in the repo, not just specific projects. Documented in `CLAUDE.md`.
- **Two memory systems in play:**
  - `Memory/` in the repo — verbose, dated session logs, committed to git. This is the primary record.
  - `~/.claude/projects/.../memory/` — Claude's auto-memory, used for quick cross-session facts (project structure, preferences, key decisions). Lighter weight.
- **Gittyup as Claude's commit tool:** Claude can commit and push by POSTing to `/gittyup/commit` with a session cookie obtained via POST `/login`. This is the preferred approach over running git commands directly.
- **Sessions app:** Claude's login sessions appear in the Sessions UI at `/sessions`. User is fine leaving them; can revoke anytime.

### Open questions / next steps
- None. Conventions are set.
