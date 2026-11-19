# Task 001 — Ingestion proof of concept

## Goal

Validate the ingestion path for collecting public AI-coding conversations
from the X API v2 recent-search endpoint **before** building trend scoring,
dashboards, or scheduled automation.

## Scope

- Single Python CLI (`python -m src.collector`), two modes:
  - `mock` — deterministic 2-page fixture, no network or credentials
  - `live` — real X API calls gated on `X_BEARER_TOKEN`
- Query topics: `Claude Code`, `Cursor`, `Codex`, `coding agent`
- Pagination via `meta.next_token`
- Retained per post: id, author id, text, timestamp, public engagement
  metrics, canonical post URL
- Storage: SQLite `posts` table, dedupe by post id (`INSERT OR IGNORE`)
- Retries: 429 honors `Retry-After` / `x-rate-limit-reset`; 5xx uses
  exponential backoff; other 4xx fails immediately

## Definition of done

- [x] `pytest -q` passes with zero network access
- [x] `python -m src.collector --mode mock --db data/posts.db` prints
      `{"pages": 2, "received": 5, "inserted": 4, "total": 4}`
- [x] Re-running the same command prints `inserted: 0, total: 4`
      (dedupe verified)
- [x] `--max-posts` and `--max-pages` caps honored
- [x] CI runs the unit tests on every push/PR

## Non-goals

- Live X API validation (needs a developer account; not yet performed)
- Multilingual keyword expansion, marketing-noise filtering (Task 002)
- Trend scoring, briefs (Task 003), delivery/scheduling (Task 004)
