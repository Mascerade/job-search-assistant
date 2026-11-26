import httpx
import pytest

from jobsearch.http import Http


def make(handler: httpx.MockTransport, sleeps: list[float], **kw: object) -> Http:
    return Http(httpx.Client(transport=handler), sleep=sleeps.append, **kw)  # type: ignore[arg-type]


def test_retries_429_with_long_backoff_then_succeeds() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(429) if len(calls) < 3 else httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    http = make(httpx.MockTransport(handler), sleeps, throttle={})
    assert http.get_json("https://acme.wd1.myworkdayjobs.com/x") == {"ok": True}
    assert len(calls) == 3
    assert sleeps[0] >= 5 and sleeps[1] >= 10  # rate-limit backoff, not the short one


def test_retry_after_header_is_respected() -> None:
    responses = [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json=[])]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    sleeps: list[float] = []
    make(httpx.MockTransport(handler), sleeps, throttle={}).get_json("https://example.com/")
    assert sleeps == [7.0]


def test_gives_up_after_retries() -> None:
    sleeps: list[float] = []
    http = make(httpx.MockTransport(lambda r: httpx.Response(429)), sleeps, throttle={}, retries=2)
    with pytest.raises(httpx.HTTPStatusError):
        http.get_json("https://example.com/")
    assert len(sleeps) == 2


def test_workday_hosts_share_one_throttle_bucket() -> None:
    sleeps: list[float] = []
    http = make(httpx.MockTransport(lambda r: httpx.Response(200, json={})), sleeps)
    http.get_json("https://harvard.wd1.myworkdayjobs.com/a")
    http.get_json("https://bmc.wd5.myworkdayjobs.com/b")  # different tenant, same bucket
    http.get_json("https://api.lever.co/v0/postings/x")  # not throttled
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 1.0
