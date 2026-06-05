"""In-house HTTP retry/backoff (H9).

A small dependency-free helper that retries transient YouTube failures
— HTTP 429 and 5xx, plus connection-level ``httpx.RequestError`` — with
exponential backoff + jitter, honoring ``Retry-After`` on 429. Kept
in-house (no tenacity) to preserve the project's lightweight runtime
footprint; the testable surface is one function with injectable sleep
and rng so unit tests run instantly and deterministically.
"""

import logging
import random
import time

import httpx

logger = logging.getLogger(__name__)

# Status codes worth retrying: rate-limit + transient server errors.
# 4xx other than 429 are caller errors and are NOT retried.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def _backoff_delay(attempt: int, base_delay: float, max_delay: float, rng) -> float:
    """Exponential backoff with full jitter: a random point in
    [0, min(base * 2**attempt, max_delay)]. Full jitter spreads
    retries from many clients instead of synchronizing them."""
    ceiling = min(base_delay * (2**attempt), max_delay)
    return ceiling * rng()


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Parse a Retry-After header (integer seconds form). YouTube uses
    the seconds form; the HTTP-date form is ignored (returns None) and
    we fall back to computed backoff."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(int(value))
    except (ValueError, TypeError):
        return None


def request_with_retries(
    send,
    *,
    retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    sleep=time.sleep,
    rng=random.random,
) -> httpx.Response:
    """Call ``send()`` (a zero-arg callable returning an
    ``httpx.Response``), retrying transient failures.

    Retries on:
      - response status in RETRYABLE_STATUS (429/5xx), and
      - ``httpx.RequestError`` (connection/timeout-class failures).

    On 429 a ``Retry-After`` header (seconds form) is honored; otherwise
    exponential backoff with full jitter is used. After ``retries``
    exhausted, the final response is returned via ``raise_for_status()``
    (which raises for a still-bad status) or the last ``RequestError``
    is re-raised.

    ``sleep`` and ``rng`` are injectable so tests run without real
    delays.
    """
    attempt = 0
    while True:
        try:
            response = send()
        except httpx.RequestError as e:
            if attempt >= retries:
                raise
            delay = _backoff_delay(attempt, base_delay, max_delay, rng)
            logger.warning(
                "Request error (%s); retrying in %.2fs (attempt %d/%d)",
                e,
                delay,
                attempt + 1,
                retries,
            )
            sleep(delay)
            attempt += 1
            continue

        if response.status_code in RETRYABLE_STATUS and attempt < retries:
            delay = _retry_after_seconds(response)
            if delay is None:
                delay = _backoff_delay(attempt, base_delay, max_delay, rng)
            logger.warning(
                "HTTP %d; retrying in %.2fs (attempt %d/%d)",
                response.status_code,
                delay,
                attempt + 1,
                retries,
            )
            sleep(delay)
            attempt += 1
            continue

        response.raise_for_status()
        return response
