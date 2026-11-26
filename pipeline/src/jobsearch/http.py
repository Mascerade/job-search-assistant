"""A polite HTTP client: generic user agent, timeouts, and retries."""

from __future__ import annotations

import time
from typing import Any

import httpx

USER_AGENT = "job-search-pipeline/0.1 (personal job search; low volume)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class Http:
    def __init__(self, client: httpx.Client | None = None, *, retries: int = 3, backoff: float = 1.5):
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            follow_redirects=True,
        )
        self.retries = retries
        self.backoff = backoff

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self.retries + 1):
            try:
                resp = self.client.request(method, url, **kwargs)
            except httpx.TransportError:
                if attempt == self.retries:
                    raise
            else:
                if resp.status_code not in RETRY_STATUS or attempt == self.retries:
                    resp.raise_for_status()
                    return resp
                retry_after = resp.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    time.sleep(min(int(retry_after), 30))
                    continue
            time.sleep(self.backoff * (2**attempt))
        raise RuntimeError("unreachable")

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.request("GET", url, **kwargs).json()

    def post_json(self, url: str, body: Any, **kwargs: Any) -> Any:
        return self.request("POST", url, json=body, **kwargs).json()

    def close(self) -> None:
        self.client.close()
