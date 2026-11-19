"""HTTP failure and backoff tests for the X API client (no real network)."""

import pytest
import requests

from src.x_client import RateLimitError, XApiError, XClient


class FakeResponse:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = "" if status_code == 200 else f"error {status_code}"

    def json(self):
        return self._payload


class FakeSession(requests.Session):
    """Session stub replaying a scripted list of responses."""

    def __init__(self, responses):
        super().__init__()
        self._responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        return self._responses.pop(0)


def make_client(responses):
    session = FakeSession(responses)
    sleeps = []
    client = XClient("test-token", session=session, sleep=sleeps.append)
    return client, session, sleeps


def test_success_returns_json():
    payload = {"data": [{"id": "1"}], "meta": {"result_count": 1}}
    client, session, _ = make_client([FakeResponse(200, payload)])
    assert client.search_recent("test query") == payload
    assert session.calls[0]["params"]["tweet.fields"] == "author_id,created_at,public_metrics"
    assert "next_token" not in session.calls[0]["params"]


def test_sends_bearer_auth_header():
    session = FakeSession([FakeResponse(200, {"data": []})])
    XClient("secret-token", session=session, sleep=lambda s: None).search_recent("q")
    assert session.headers["Authorization"] == "Bearer secret-token"


def test_429_retries_with_retry_after_hint():
    responses = [
        FakeResponse(429, headers={"Retry-After": "7"}),
        FakeResponse(200, {"data": []}),
    ]
    client, _, sleeps = make_client(responses)
    client.search_recent("q")
    assert sleeps == [7.0]


def test_429_retries_with_rate_limit_reset():
    responses = [
        FakeResponse(429, headers={"x-rate-limit-reset": "9999999999"}),
        FakeResponse(200, {"data": []}),
    ]
    client, _, sleeps = make_client(responses)
    client.search_recent("q")
    assert len(sleeps) == 1
    # reset is far in the future, so the wait is capped at MAX_BACKOFF_SECONDS
    assert sleeps[0] == 300.0


def test_429_exhausts_retries_and_raises():
    responses = [FakeResponse(429) for _ in range(4)]
    client, _, sleeps = make_client(responses)
    with pytest.raises(RateLimitError):
        client.search_recent("q")
    assert sleeps == [1.0, 2.0, 4.0]


def test_5xx_retries_then_succeeds():
    responses = [FakeResponse(500), FakeResponse(503), FakeResponse(200, {"data": []})]
    client, _, sleeps = make_client(responses)
    assert client.search_recent("q") == {"data": []}
    assert sleeps == [1.0, 2.0]


def test_5xx_exhausts_retries_and_raises():
    client, _, _ = make_client([FakeResponse(500) for _ in range(4)])
    with pytest.raises(XApiError):
        client.search_recent("q")


def test_4xx_raises_immediately_without_retry():
    responses = [FakeResponse(400)]
    client, session, sleeps = make_client(responses)
    with pytest.raises(XApiError, match="400"):
        client.search_recent("q")
    assert len(session.calls) == 1
    assert sleeps == []


def test_pagination_param_passed_through():
    session = FakeSession([FakeResponse(200, {"data": []})])
    XClient("t", session=session, sleep=lambda s: None).search_recent(
        "q", next_token="tok123", max_results=80
    )
    params = session.calls[0]["params"]
    assert params["next_token"] == "tok123"
    assert params["max_results"] == 80


def test_max_results_clamped_to_api_bounds():
    session = FakeSession([FakeResponse(200, {"data": []})])
    XClient("t", session=session, sleep=lambda s: None).search_recent(
        "q", max_results=500
    )
    assert session.calls[0]["params"]["max_results"] == 100
