# Actor Overlap — Session Log

## 2026-05-07 — Initial Build

### What was built
Full Actor Overlap app at `/actoroverlap`. User enters two movie or TV show titles; app returns any actors credited in both.

### Tech decisions
- **TMDB API** chosen over Claude-as-data-source for accuracy. User obtained a free TMDB Read Access Token (JWT Bearer).
- **Only credited cast** — no crew, directors, writers.
- **Plays excluded** — TMDB doesn't cover theater; keeping scope to movies and TV.
- For TV shows, uses `/tv/{id}/aggregate_credits` (covers all seasons/episodes) rather than `/credits` (series regulars only). This is the right call for shows with large rotating casts.
- Person matching done by **TMDB person ID**, not name — reliable even when actors share names.
- API key stored in `webapp/.env` as `TMDB_API_KEY`.

### UX design
- Mobile-first, iPhone-optimized throughout (large touch targets, `-webkit-tap-highlight-color`, `-webkit-overflow-scrolling: touch`, no hover-only interactions).
- Live autocomplete dropdowns (debounced 280ms) show poster thumbnail + year + type (Movie / TV Series).
- Selecting a result locks it into a card; "✕ change" lets user swap it.
- "Find Overlap" button disabled until both titles are locked.
- Results show actor photo, name, and character name in each property.
- Two-column grid on desktop, single column on mobile.

### Deployment
- Committed and pushed via Gittyup API (Claude logged in via POST `/login`, then POST `/gittyup/commit`).
- Gunicorn reloaded via `kill -HUP` on master PID.

### Open questions / next steps
- No pagination on results — if two ensemble shows share a huge cast this could get long. Not a problem yet.
- Could add a "did you mean?" flow if TMDB search returns a low-confidence top result. Currently relies on user recognizing the right match from the dropdown.
