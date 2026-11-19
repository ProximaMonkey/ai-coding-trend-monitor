"""CLI entry point: paginated collection of AI-coding posts into SQLite.

Usage:
    python -m src.collector --mode mock --db data/posts.db
    python -m src.collector --mode live --db data/live_posts.db \
        --max-posts 80 --max-pages 3
"""

import argparse
import json
import os
from contextlib import contextmanager
from pathlib import Path

from . import storage
from .x_client import XClient

QUERY = '("Claude Code" OR Cursor OR Codex OR "coding agent") -is:retweet'

DEFAULT_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "pages.json"


class MockClient:
    """Deterministic fixture-backed client; no network, no credentials."""

    def __init__(self, fixture_path=DEFAULT_FIXTURE):
        payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        self._pages = payload["pages"]

    def search_recent(self, query, next_token=None, max_results=100):
        index = 0 if next_token is None else int(next_token)
        if index >= len(self._pages):
            return {"data": [], "meta": {"result_count": 0}}
        return self._pages[index]


def normalize_post(tweet):
    metrics = tweet.get("public_metrics") or {}
    return {
        "id": str(tweet["id"]),
        "author_id": str(tweet.get("author_id", "")),
        "text": tweet.get("text", ""),
        "created_at": tweet.get("created_at", ""),
        "retweet_count": int(metrics.get("retweet_count", 0)),
        "reply_count": int(metrics.get("reply_count", 0)),
        "like_count": int(metrics.get("like_count", 0)),
        "quote_count": int(metrics.get("quote_count", 0)),
        "url": f"https://x.com/i/web/status/{tweet['id']}",
    }


@contextmanager
def _write_txn(conn):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def collect(client, conn, query=QUERY, max_posts=None, max_pages=None):
    """Run the paginated collection loop. Returns a JSON-serializable summary."""
    pages = 0
    received = 0
    inserted = 0
    next_token = None

    # Each page commits independently: a later fetch failure keeps earlier
    # posts, and network/retry waits never hold the writer lock. The cap
    # check and inserts stay inside one transaction so concurrent runs
    # serialize and cannot overshoot max_posts.
    conn.isolation_level = None

    while True:
        if max_pages is not None and pages >= max_pages:
            break
        with _write_txn(conn):
            capped = max_posts is not None and storage.count_posts(conn) >= max_posts
        if capped:
            break

        try:
            page = client.search_recent(query, next_token=next_token)
        except Exception:
            # A concurrent run may have filled the cap while we retried;
            # in that case exit cleanly rather than propagating the error.
            with _write_txn(conn):
                capped = max_posts is not None and storage.count_posts(conn) >= max_posts
            if capped:
                break
            raise
        pages += 1

        with _write_txn(conn):
            for tweet in page.get("data", []):
                received += 1
                if max_posts is not None and storage.count_posts(conn) >= max_posts:
                    continue
                if storage.insert_post(conn, normalize_post(tweet)):
                    inserted += 1

        next_token = (page.get("meta") or {}).get("next_token")
        if not next_token:
            break

    return {
        "pages": pages,
        "received": received,
        "inserted": inserted,
        "total": storage.count_posts(conn),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="collector",
        description="Collect public AI-coding posts into SQLite.",
    )
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--db", required=True, help="SQLite database path")
    parser.add_argument("--max-posts", type=int, default=None,
                        help="Stop once this many posts are stored")
    parser.add_argument("--max-pages", type=int, default=None,
                        help="Stop after fetching this many result pages")
    parser.add_argument("--fixture", default=None,
                        help="Mock-mode fixture path (default: bundled pages.json)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.mode == "live":
        token = os.environ.get("X_BEARER_TOKEN")
        if not token:
            raise SystemExit("live mode requires X_BEARER_TOKEN in the environment")
        client = XClient(token)
    else:
        client = MockClient(args.fixture or DEFAULT_FIXTURE)

    conn = storage.connect(args.db)
    try:
        summary = collect(
            client,
            conn,
            max_posts=args.max_posts,
            max_pages=args.max_pages,
        )
    finally:
        conn.close()
    print(json.dumps(summary))
    return summary


if __name__ == "__main__":
    main()
