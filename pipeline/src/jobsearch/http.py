"""A polite HTTP client: generic user agent, timeouts, per-site throttling, and retries."""

from __future__ import annotations

import random
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

USER_AGENT = "job-search-pipeline/0.1 (personal job search; low volume)"
RETRY_STATUS = {429, 500, 502, 503, 504}

# Minimum seconds between requests to each group of hosts. Every *.myworkdayjobs.com
# site runs on shared Workday infrastructure that rate-limits cloud IPs (GitHub Actions
# got 429s with parallel requests), so all Workday traffic takes turns.
# Adzuna's free tier has per-minute limits (shown in your Adzuna account); stay well under.
DEFAULT_THROTTLE: Mapping[str, float] = {"myworkdayjobs.com": 1.0, "api.adzuna.com": 2.5, "avature.net": 0.5}


class Http:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        retries: int = 4,
        backoff: float = 1.5,
        rate_limit_backoff: float = 5.0,
        throttle: Mapping[str, float] = DEFAULT_THROTTLE,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
        self.retries = retries
        self.backoff = backoff
        self.rate_limit_backoff = rate_limit_backoff
        self.throttle = dict(throttle)
        self.sleep = sleep
        self._locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        self._last: dict[str, float] = {}

    def _wait_turn(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        for suffix, interval in self.throttle.items():
            if host == suffix or host.endswith("." + suffix):
                # Holding the lock while sleeping serializes this group across threads.
                with self._locks[suffix]:
                    wait = self._last.get(suffix, 0.0) + interval - time.monotonic()
                    if wait > 0:
                        self.sleep(wait)
                    self._last[suffix] = time.monotonic()
                return

    def _delay(self, resp: httpx.Response | None, attempt: int) -> float:
        if resp is not None and resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                return min(float(retry_after), 60.0)
            return min(self.rate_limit_backoff * 2.0**attempt, 60.0) + random.uniform(0, 1)
        return self.backoff * 2.0**attempt

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self.retries + 1):
            self._wait_turn(url)
            resp: httpx.Response | None = None
            try:
                resp = self.client.request(method, url, **kwargs)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
            else:
                if resp.status_code not in RETRY_STATUS or attempt == self.retries:
                    resp.raise_for_status()
                    return resp
            self.sleep(self._delay(resp, attempt))
        raise RuntimeError("unreachable")

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.request("GET", url, **kwargs).json()

    def post_json(self, url: str, body: Any, **kwargs: Any) -> Any:
        return self.request("POST", url, json=body, **kwargs).json()

    def close(self) -> None:
        self.client.close()
