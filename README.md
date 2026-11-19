# AI Coding Trend Monitor

A small, testable proof of concept for collecting public AI coding conversations using the **X API v2 recent search** endpoint. Its purpose is to validate ingestion before building any AI trend scoring or dashboards.

> **Status (Task 001):** mock pipeline implemented and unit-tested. Live X API validation has **not** been performed. This repository is not evidence of full X coverage, or of any deployed automation.

## Current scope

- Query topics: `Claude Code`, `Cursor`, `Codex`, `coding agent`
- Fetch X recent search results from the past 24 hours when live credentials are provided
- Pagination (`meta.next_token`), row deduplication, SQLite storage
- Retain author IDs, text, timestamps, public engagement metrics, original post URL
- Retry 429 / 5xx responses with rate-limit-aware backoff
- Fixture-only reproducible tests; no network or X billing in tests

## Quickstart - no API credentials required

Requires Python 3.10+.

```bash
python -m pip install -e '.[dev]'
pytest -q
python -m src.collector --mode mock --db data/posts.db
python -m src.collector --mode mock --db data/posts.db
```

Expected CLI summaries:

```json
{"pages": 2, "received": 5, "inserted": 4, "total": 4}
{"pages": 2, "received": 5, "inserted": 0, "total": 4}
```

Mock data is synthetic, not scraped from X.

## Live collection - requires an X developer account

```bash
export X_BEARER_TOKEN='YOUR_SECRET'
python -m src.collector --mode live --db data/live_posts.db --max-posts 80 --max-pages 3
```

The collector reads the token from the environment and never logs it. **Do not paste credentials into public issues or commits.** Only query public material and comply with X API terms, access rights, and billing limits. A max-post cap limits stored posts, not necessarily the number of posts read or billed by the API, so configure usage/spending controls at the provider too.

Current implementation uses a CLI rather than a background scheduler. No LLM filtering or notifications yet.

## Design

```text
X API Recent Search (or deterministic fixture)
                  |
                  v
     Paginated Python collector
                  |
                  v
          SQLite posts table
```

## Project layout

```text
src/collector.py          CLI / pagination / mock client
src/x_client.py           X API client / 429 retry
src/storage.py            SQLite schema / dedupe
tests/fixtures/pages.json Synthetic 2-page API response
tests/test_collector.py   Ingestion acceptance tests
tests/test_x_client.py    HTTP failure and backoff tests
docs/TASK-001.md          Devin Task 001 + definition of done
.github/workflows/ci.yml Unit-test CI
```

## Next milestones

- Task 002: multilingual keyword expansion and source-quality/marketing-noise filtering
- Task 003: topic clustering, trend scoring, and verifiable daily briefs
- Task 004: Feishu delivery, scheduled runs, operational metrics

The emphasis is on independently verifiable developer discussion, not just trending keywords.
