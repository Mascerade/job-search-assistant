"""Handle website button presses the moment they happen (Supabase Realtime = websockets).

    uv run jobsearch listen

The website inserts a row into `tasks` (Tailor now / Regenerate / build PDFs). This
process keeps a websocket open to Supabase Realtime; every INSERT on `tasks` wakes it
up, and it runs process_tasks() right away. As safety nets it also:
  - processes anything already queued when it starts (e.g. after the Mac wakes up),
  - sweeps every few minutes in case an event was missed,
  - exits if the connection is lost for good, so launchd (KeepAlive) restarts it.

Tasks are claimed atomically (queued → working) before processing, so a task is
never handled twice even if two runners overlap.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from realtime import RealtimePostgresChangesListenEvent, RealtimeSubscribeStates
from supabase import acreate_client

from .config import load_config

log = logging.getLogger("jobsearch.listener")

SWEEP_SECONDS = 300
BATCH = 10


async def listen(*, max_seconds: float | None = None) -> None:
    from .documents import process_tasks

    cfg = load_config()
    client = await acreate_client(cfg.supabase_url, cfg.supabase_secret_key)
    wake = asyncio.Event()
    lost = asyncio.Event()

    def on_insert(_payload: Any) -> None:
        wake.set()

    def on_status(state: RealtimeSubscribeStates, err: Exception | None) -> None:
        log.info("realtime channel: %s%s", state.name, f" ({err})" if err else "")
        if state != RealtimeSubscribeStates.SUBSCRIBED:
            lost.set()
            wake.set()

    channel = client.channel("job-search-tasks")
    channel.on_postgres_changes(
        RealtimePostgresChangesListenEvent.Insert, on_insert, table="tasks", schema="public"
    )
    await channel.subscribe(on_status)
    log.info("listening for website requests (sweep every %ss)", SWEEP_SECONDS)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_seconds if max_seconds else None
    wake.set()  # catch up on anything queued while we weren't running
    try:
        while True:
            timeout: float = SWEEP_SECONDS
            if deadline is not None:
                timeout = min(timeout, max(deadline - loop.time(), 0))
                if timeout == 0:
                    return
            with contextlib.suppress(TimeoutError):  # a timeout is just the periodic sweep
                await asyncio.wait_for(wake.wait(), timeout=timeout)
            wake.clear()
            if lost.is_set() and not client.realtime.is_connected:
                raise ConnectionError(
                    "lost the Realtime connection; exiting so launchd restarts the listener"
                )
            try:
                lines = await asyncio.to_thread(process_tasks, BATCH)
            except Exception:  # keep listening; the task row records the error for the website
                log.exception("processing tasks failed")
                continue
            for line in lines:
                log.info("task: %s", line)
            if len(lines) >= BATCH:
                wake.set()  # more may be waiting
    finally:
        await client.realtime.close()


def run(max_seconds: float | None = None) -> None:
    asyncio.run(listen(max_seconds=max_seconds))
