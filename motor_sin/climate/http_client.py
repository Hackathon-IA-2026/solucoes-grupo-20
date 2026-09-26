from __future__ import annotations

import json
import time
from dataclasses import dataclass, asdict
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class OpenMeteoRateLimitDeferred(RuntimeError):
    """Raised when the provider keeps returning HTTP 429 after the configured retries.

    This is intentionally distinct from a generic HTTP error: callers can persist a
    checkpoint and defer/resume the exact same download later without marking the
    scientific pipeline as corrupt.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None, stats: dict[str, Any] | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.stats = stats or {}


@dataclass
class _RateLimitState:
    consecutive_429: int = 0
    total_429: int = 0
    cooldowns: int = 0
    last_status: int | None = None


_RATE_LIMIT_STATE = _RateLimitState()


def reset_rate_limit_state() -> None:
    global _RATE_LIMIT_STATE
    _RATE_LIMIT_STATE = _RateLimitState()


def rate_limit_stats() -> dict[str, int | None]:
    return asdict(_RATE_LIMIT_STATE)


def _retry_after_seconds(exc: HTTPError) -> float | None:
    value = exc.headers.get('Retry-After') if exc.headers else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            dt = parsedate_to_datetime(value)
            return max(0.0, dt.timestamp() - time.time())
        except Exception:
            return None


def fetch_json_with_retry(
    url: str,
    *,
    timeout_seconds: int = 90,
    user_agent: str = 'predicta-hackathon/1.11.1',
    max_retries: int = 10,
    base_backoff_seconds: float = 10.0,
    max_backoff_seconds: float = 180.0,
    cooldown_after_429: int = 3,
    global_cooldown_seconds: float = 90.0,
) -> tuple[int, Any]:
    """GET JSON with exponential retry and process-wide 429 cooldown.

    If the 429 persists after the retry budget, raise ``OpenMeteoRateLimitDeferred``
    instead of leaking a raw ``HTTPError``. Higher-level orchestration can then mark
    the run as WAITING_RATE_LIMIT and resume from the immutable point/year cache.
    """
    attempt = 0
    last_retry_after: float | None = None
    while True:
        request = Request(
            url,
            headers={'Accept': 'application/json', 'User-Agent': user_agent},
            method='GET',
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310 fixed HTTPS endpoint
                status = int(response.status)
                body = response.read().decode('utf-8')
            payload = json.loads(body)
            if status >= 400:
                raise RuntimeError(f'HTTP status={status} payload={payload}')
            _RATE_LIMIT_STATE.consecutive_429 = 0
            _RATE_LIMIT_STATE.last_status = status
            return status, payload
        except HTTPError as exc:
            attempt += 1
            _RATE_LIMIT_STATE.last_status = int(exc.code)
            if exc.code == 429:
                _RATE_LIMIT_STATE.consecutive_429 += 1
                _RATE_LIMIT_STATE.total_429 += 1
            else:
                _RATE_LIMIT_STATE.consecutive_429 = 0
            retry_after = _retry_after_seconds(exc)
            last_retry_after = retry_after if retry_after is not None else last_retry_after
            if exc.code not in RETRYABLE_STATUS:
                raise
            if attempt > max_retries:
                if exc.code == 429:
                    suggested = max(float(global_cooldown_seconds), float(last_retry_after or 0.0), 900.0)
                    raise OpenMeteoRateLimitDeferred(
                        f'Open-Meteo continued returning HTTP 429 after {max_retries} retries; '
                        f'checkpoint is safe to resume later (suggested wait >= {suggested:.0f}s)',
                        retry_after_seconds=suggested,
                        stats=rate_limit_stats(),
                    ) from exc
                raise
            backoff = min(max_backoff_seconds, base_backoff_seconds * (2 ** (attempt - 1)))
            wait = max(backoff, retry_after or 0.0)
            if (
                exc.code == 429
                and cooldown_after_429 > 0
                and _RATE_LIMIT_STATE.consecutive_429 >= int(cooldown_after_429)
            ):
                wait = max(wait, float(global_cooldown_seconds))
                _RATE_LIMIT_STATE.cooldowns += 1
                print(
                    f'Open-Meteo global cooldown after {_RATE_LIMIT_STATE.consecutive_429} consecutive 429s; '
                    f'pausing {wait:.1f}s before retry',
                    flush=True,
                )
                _RATE_LIMIT_STATE.consecutive_429 = 0
            else:
                print(
                    f'Open-Meteo HTTP {exc.code}; retry {attempt}/{max_retries} in {wait:.1f}s',
                    flush=True,
                )
            time.sleep(wait)
        except (URLError, TimeoutError, OSError) as exc:
            attempt += 1
            _RATE_LIMIT_STATE.consecutive_429 = 0
            if attempt > max_retries:
                raise
            wait = min(max_backoff_seconds, base_backoff_seconds * (2 ** (attempt - 1)))
            print(
                f'Open-Meteo transient error {type(exc).__name__}; retry {attempt}/{max_retries} in {wait:.1f}s',
                flush=True,
            )
            time.sleep(wait)
