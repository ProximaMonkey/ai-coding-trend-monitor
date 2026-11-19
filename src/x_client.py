"""Minimal X API v2 recent-search client with rate-limit-aware retries."""

import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

RECENT_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
TWEET_FIELDS = "author_id,created_at,public_metrics"

# Upper bound on any single wait so a misbehaving API cannot stall a run.
MAX_BACKOFF_SECONDS = 300.0


class XApiError(Exception):
    """Non-retryable X API failure."""


class RateLimitError(XApiError):
    """Retry budget exhausted on HTTP 429."""


class XClient:
    def __init__(self, bearer_token, session=None, max_retries=3, sleep=time.sleep):
        if not bearer_token:
            raise ValueError("bearer_token is required")
        self._session = session or requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {bearer_token}"})
        self._max_retries = max_retries
        self._sleep = sleep

    def search_recent(self, query, next_token=None, max_results=100):
        start_time = datetime.now(timezone.utc) - timedelta(hours=24)
        params = {
            "query": query,
            "max_results": max(10, min(int(max_results), 100)),
            "tweet.fields": TWEET_FIELDS,
            "start_time": start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if next_token:
            params["next_token"] = next_token

        for attempt in range(self._max_retries + 1):
            resp = self._session.get(RECENT_SEARCH_URL, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                if attempt >= self._max_retries:
                    raise RateLimitError(
                        f"X API rate limited after {attempt + 1} attempts"
                    )
                self._sleep(self._retry_wait(resp, attempt))
                continue
            if 500 <= resp.status_code < 600:
                if attempt >= self._max_retries:
                    raise XApiError(
                        f"X API server error {resp.status_code} after "
                        f"{attempt + 1} attempts"
                    )
                self._sleep(min(2.0**attempt, MAX_BACKOFF_SECONDS))
                continue
            raise XApiError(
                f"X API error {resp.status_code}: {resp.text[:200]}"
            )
        raise XApiError("unreachable")  # pragma: no cover

    @staticmethod
    def _retry_wait(resp, attempt):
        """Seconds to wait after a 429: server hints first, else exponential."""
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            if retry_after.isdigit():
                return min(float(retry_after), MAX_BACKOFF_SECONDS)
            try:
                retry_dt = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError):
                retry_dt = None
            if retry_dt is not None:
                if retry_dt.tzinfo is None:
                    retry_dt = retry_dt.replace(tzinfo=timezone.utc)
                wait = (retry_dt - datetime.now(timezone.utc)).total_seconds()
                return min(max(wait, 1.0), MAX_BACKOFF_SECONDS)
        reset = resp.headers.get("x-rate-limit-reset")
        if reset and reset.isdigit():
            return min(max(float(reset) - time.time(), 1.0), MAX_BACKOFF_SECONDS)
        return min(2.0**attempt, MAX_BACKOFF_SECONDS)
