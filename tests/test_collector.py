"""Ingestion acceptance tests for the collector pipeline (fixture-only)."""

import json
from pathlib import Path

import pytest

from src import storage
from src.collector import DEFAULT_FIXTURE, MockClient, collect, main


@pytest.fixture()
def conn(tmp_path):
    connection = storage.connect(tmp_path / "posts.db")
    yield connection
    connection.close()


def test_default_fixture_is_packaged():
    # Regression: the mock fixture must ship inside the installed package.
    assert Path(DEFAULT_FIXTURE).is_file()


def test_first_run_inserts_unique_posts(conn):
    summary = collect(MockClient(), conn)
    assert summary == {"pages": 2, "received": 5, "inserted": 4, "total": 4}


def test_second_run_dedupes_everything(conn):
    collect(MockClient(), conn)
    summary = collect(MockClient(), conn)
    assert summary == {"pages": 2, "received": 5, "inserted": 0, "total": 4}


def test_stored_rows_have_required_fields(conn):
    collect(MockClient(), conn)
    rows = conn.execute(
        "SELECT id, author_id, text, created_at, url, like_count FROM posts"
    ).fetchall()
    assert len(rows) == 4
    for post_id, author_id, text, created_at, url, like_count in rows:
        assert post_id and author_id and text and created_at
        assert url == f"https://x.com/i/web/status/{post_id}"
        assert isinstance(like_count, int)


def test_max_pages_stops_pagination(conn):
    summary = collect(MockClient(), conn, max_pages=1)
    assert summary["pages"] == 1
    assert summary["received"] == 3
    assert summary["total"] == 3


def test_max_posts_caps_stored_rows(conn):
    summary = collect(MockClient(), conn, max_posts=2)
    assert summary["total"] == 2
    assert summary["inserted"] == 2


def test_later_page_failure_keeps_committed_posts(conn):
    class FailsOnSecondPage(MockClient):
        def search_recent(self, query, next_token=None, max_results=100):
            if next_token is not None:
                raise RuntimeError("simulated fetch failure")
            return super().search_recent(query, next_token, max_results)

    with pytest.raises(RuntimeError):
        collect(FailsOnSecondPage(), conn)
    assert storage.count_posts(conn) == 3


def test_cli_mock_mode_prints_summary(tmp_path, capsys):
    db = tmp_path / "cli.db"
    main(["--mode", "mock", "--db", str(db)])
    out = json.loads(capsys.readouterr().out.strip())
    assert out == {"pages": 2, "received": 5, "inserted": 4, "total": 4}
    main(["--mode", "mock", "--db", str(db)])
    out = json.loads(capsys.readouterr().out.strip())
    assert out["inserted"] == 0 and out["total"] == 4
