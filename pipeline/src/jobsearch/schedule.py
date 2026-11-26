"""The Mac's daily job, as a macOS LaunchAgent.

    uv run jobsearch schedule install [--at 07:30]   # write + load the LaunchAgent
    uv run jobsearch schedule run-now                 # run it once in the background, as launchd would
    uv run jobsearch schedule status                  # loaded? last exit code? recent log lines
    uv run jobsearch schedule uninstall

The agent runs `jobsearch local-daily` against production: fetch the Workday boards
(they block cloud servers) and score new jobs with Claude Code. If the Mac is asleep
at the scheduled time, launchd runs the job when it wakes.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import PIPELINE_DIR
from .llm import claude_binary

LABEL = "com.jobsearchassistant.local-daily"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = Path.home() / "Library" / "Logs" / "jobsearch-local-daily.log"
# A second, tiny agent: every 10 minutes, handle button presses from the website
# (render after approval, regenerate, tailor now). Exits immediately when there are none.
TASKS_LABEL = "com.jobsearchassistant.tasks"
TASKS_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{TASKS_LABEL}.plist"
TASKS_LOG = Path.home() / "Library" / "Logs" / "jobsearch-tasks.log"
TASKS_EVERY_S = 600


def _domain() -> str:
    return f"gui/{os.getuid()}"


def plist_dict(hour: int, minute: int, uv: str, claude: str) -> dict[str, Any]:
    path_dirs = [str(Path(uv).parent), str(Path(claude).parent), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    return {
        "Label": LABEL,
        "ProgramArguments": [uv, "run", "--project", str(PIPELINE_DIR), "jobsearch", "local-daily"],
        "WorkingDirectory": str(PIPELINE_DIR),
        "EnvironmentVariables": {
            "JOBSEARCH_ENV": "production",
            "CLAUDE_BIN": claude,
            "PATH": ":".join(dict.fromkeys(path_dirs)),
        },
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
        "ProcessType": "Background",
    }


def tasks_plist_dict(uv: str, claude: str) -> dict[str, Any]:
    d = plist_dict(0, 0, uv, claude)
    del d["StartCalendarInterval"]
    d.update(
        Label=TASKS_LABEL,
        ProgramArguments=[uv, "run", "--project", str(PIPELINE_DIR), "jobsearch", "tasks"],
        StartInterval=TASKS_EVERY_S,
        StandardOutPath=str(TASKS_LOG),
        StandardErrorPath=str(TASKS_LOG),
    )
    return d


def _launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=False)


def install(hour: int = 7, minute: int = 30) -> Path:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv not found on PATH")
    data = plist_dict(hour, minute, uv, claude_binary())
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    for plist, contents in ((PLIST, data), (TASKS_PLIST, tasks_plist_dict(uv, claude_binary()))):
        plist.write_bytes(plistlib.dumps(contents))
        _launchctl("bootout", _domain(), str(plist))  # reload if it was already installed
        result = _launchctl("bootstrap", _domain(), str(plist))
        if result.returncode != 0:
            raise RuntimeError(f"launchctl bootstrap failed for {plist.name}: {result.stderr.strip()}")
    return PLIST


def uninstall() -> bool:
    removed = False
    for plist in (PLIST, TASKS_PLIST):
        _launchctl("bootout", _domain(), str(plist))
        if plist.exists():
            plist.unlink()
            removed = True
    return removed


def run_now() -> None:
    result = _launchctl("kickstart", f"{_domain()}/{LABEL}")
    if result.returncode != 0:
        raise RuntimeError(f"launchctl kickstart failed (is it installed?): {result.stderr.strip()}")


def status() -> str:
    if not PLIST.exists():
        return "Not installed. Run: uv run jobsearch schedule install"
    info = _launchctl("print", f"{_domain()}/{LABEL}")
    lines = [f"Installed: {PLIST}"]
    if info.returncode != 0:
        lines.append("Not loaded in launchd (try `schedule install` again).")
    else:
        for line in info.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith(("state =", "last exit code =", "runs =")):
                lines.append(stripped)
    when = plistlib.loads(PLIST.read_bytes()).get("StartCalendarInterval", {})
    lines.append(
        f"Runs daily at {when.get('Hour', 0):02d}:{when.get('Minute', 0):02d} (or on wake if asleep then)"
    )
    tasks_state = _launchctl("print", f"{_domain()}/{TASKS_LABEL}")
    lines.append(
        f"Task checker (every {TASKS_EVERY_S // 60} min): "
        + ("loaded" if tasks_state.returncode == 0 else "not loaded — run `schedule install`")
    )
    if LOG.exists():
        tail = LOG.read_text(errors="replace").splitlines()[-8:]
        lines.append(f"Last log lines ({LOG}):")
        lines.extend(f"  {t}" for t in tail)
    return "\n".join(lines)
