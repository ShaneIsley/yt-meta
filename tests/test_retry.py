"""Unit tests for the in-house retry/backoff helper (H9)."""

import httpx
import pytest

from yt_meta._retry import request_with_retries


def _response(status: int, headers=None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, request=httpx.Request("GET", "https://x"))


def test_h9_returns_immediately_on_success():
    calls = []

    def send():
        calls.append(1)
        return _response(200)

    resp = request_with_retries(send, sleep=lambda _: None)
    assert resp.status_code == 200
    assert len(calls) == 1  # no retries on success


def test_h9_retries_on_503_then_succeeds():
    responses = [_response(503), _response(503), _response(200)]
    slept = []

    def send():
        return responses.pop(0)

    resp = request_with_retries(
        send, retries=3, sleep=slept.append, rng=lambda: 1.0
    )
    assert resp.status_code == 200
    assert len(slept) == 2  # two backoff sleeps before the 200


def test_h9_retries_on_429_and_honors_retry_after():
    responses = [_response(429, {"Retry-After": "7"}), _response(200)]
    slept = []

    request_with_retries(
        lambda: responses.pop(0), retries=3, sleep=slept.append, rng=lambda: 1.0
    )
    assert slept == [7.0]  # used the Retry-After value, not computed backoff


def test_h9_gives_up_after_retries_and_raises():
    def send():
        return _response(503)

    with pytest.raises(httpx.HTTPStatusError):
        request_with_retries(send, retries=2, sleep=lambda _: None, rng=lambda: 1.0)


def test_h9_retries_on_request_error_then_succeeds():
    calls = []

    def send():
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("boom")
        return _response(200)

    resp = request_with_retries(
        send, retries=3, sleep=lambda _: None, rng=lambda: 1.0
    )
    assert resp.status_code == 200
    assert len(calls) == 3


def test_h9_reraises_request_error_after_exhausting_retries():
    def send():
        raise httpx.ConnectTimeout("nope")

    with pytest.raises(httpx.ConnectTimeout):
        request_with_retries(send, retries=2, sleep=lambda _: None, rng=lambda: 1.0)


def test_h9_does_not_retry_4xx_other_than_429():
    """A 404 is a caller error — surface it immediately, no retries."""
    calls = []

    def send():
        calls.append(1)
        return _response(404)

    with pytest.raises(httpx.HTTPStatusError):
        request_with_retries(send, retries=3, sleep=lambda _: None)
    assert len(calls) == 1  # never retried


def test_h9_backoff_grows_exponentially_with_full_jitter():
    """With rng pinned to 1.0 (jitter ceiling), successive delays should
    be base, base*2, base*4 ... capped at max_delay."""
    responses = [_response(500), _response(500), _response(500), _response(200)]
    slept = []
    request_with_retries(
        lambda: responses.pop(0),
        retries=5,
        base_delay=1.0,
        max_delay=30.0,
        sleep=slept.append,
        rng=lambda: 1.0,
    )
    assert slept == [1.0, 2.0, 4.0]
