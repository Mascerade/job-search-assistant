"""Command-line entry point: `uv run jobsearch <command>`.

Commands:
  jobsearch daily [--dry-run] [--only TOKEN ...]   fetch every job board, filter, and save
  jobsearch owner create --email you@example.com   register the one account allowed to sign in
  jobsearch profile validate [PATH]                check a profile YAML file
  jobsearch profile push [PATH] --note "..."       upload it as a new profile version
  jobsearch profile pull                           print the current profile as YAML
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import ValidationError

from .config import REPO_DIR, ConfigError
from .profile import Profile, load_profile, profile_from_data

DEFAULT_PROFILE = REPO_DIR / "private" / "profile.yaml"


def _cmd_owner_create(args: argparse.Namespace) -> int:
    from . import db

    user_id, created = db.ensure_owner(args.email)
    verb = "Created" if created else "Found existing"
    print(f"{verb} account {args.email} ({user_id}) and registered it as the site owner.")
    return 0


def _load_or_report(path: Path) -> Profile | None:
    try:
        return load_profile(path)
    except FileNotFoundError:
        print(f"No profile at {path}", file=sys.stderr)
    except ValidationError as e:
        print(f"{path} has problems:", file=sys.stderr)
        for err in e.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "(top level)"
            print(f"  - {loc}: {err['msg']}", file=sys.stderr)
    return None


def _cmd_profile_validate(args: argparse.Namespace) -> int:
    profile = _load_or_report(args.path)
    if profile is None:
        return 1
    print(
        f"OK: {len(profile.experience)} experience, {len(profile.projects)} projects, "
        f"{len(profile.all_facts())} facts, {len(profile.all_skills())} skills."
    )
    return 0


def _cmd_profile_push(args: argparse.Namespace) -> int:
    from . import db

    profile = _load_or_report(args.path)
    if profile is None:
        return 1
    version = db.insert_profile(profile.model_dump(mode="json", exclude_defaults=True), args.note)
    print(f"Uploaded profile as version {version}.")
    return 0


def _cmd_profile_pull(_args: argparse.Namespace) -> int:
    from . import db

    row = db.latest_profile()
    if row is None:
        print("No profile uploaded yet.", file=sys.stderr)
        return 1
    print(f"# version {row.version} ({row.created_at:%Y-%m-%d %H:%M}) {row.note}".rstrip())
    # Postgres jsonb doesn't keep key order; re-dump through the model for a readable layout.
    data = profile_from_data(row.data).model_dump(mode="json", exclude_defaults=True)
    print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
    return 0


def _cmd_daily(args: argparse.Namespace) -> int:
    from .daily import run_daily

    summary = run_daily(dry_run=args.dry_run, only=args.only or None)
    c = summary.counts
    print(
        f"Boards: {c['boards_ok']} ok, {c['boards_failed']} failed | postings fetched: {c['fetched']} | "
        f"kept: {c['kept']} | filtered: title {c['filtered_title']}, location {c['filtered_location']}, "
        f"details {c['filtered_detail']}"
    )
    if not args.dry_run:
        print(
            f"Saved: {c['inserted']} new, {c['updated']} updated, {c['duplicates']} duplicates skipped, "
            f"{c['closed']} closed"
        )
    for err in summary.errors:
        print(f"  ! {err}", file=sys.stderr)
    if args.dry_run and summary.kept and args.show > 0:
        print("\nWould keep:")
        for p, v in sorted(summary.kept, key=lambda pv: (pv[1].track or "", pv[0].company))[: args.show]:
            print(f"  [{v.track}] {p.company} — {p.title} — {p.location or '?'}")
        if len(summary.kept) > args.show:
            print(f"  … and {len(summary.kept) - args.show} more")
    return 1 if c["boards_ok"] == 0 and summary.errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobsearch", description="Job search assistant pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser("daily", help="run the daily job feed")
    daily.add_argument("--dry-run", action="store_true", help="fetch and filter, but write nothing")
    daily.add_argument("--only", nargs="*", help="limit to boards by token, key, or company name")
    daily.add_argument("--show", type=int, default=60, help="how many kept jobs to list in a dry run")
    daily.set_defaults(func=_cmd_daily)

    owner = sub.add_parser("owner", help="manage the owner account").add_subparsers(
        dest="action", required=True
    )
    create = owner.add_parser("create", help="create/register the single owner account")
    create.add_argument("--email", required=True)
    create.set_defaults(func=_cmd_owner_create)

    prof = sub.add_parser("profile", help="master profile").add_subparsers(dest="action", required=True)
    for name, func, helptext in (
        ("validate", _cmd_profile_validate, "check a profile YAML file"),
        ("push", _cmd_profile_push, "upload a profile YAML file as a new version"),
    ):
        p = prof.add_parser(name, help=helptext)
        p.add_argument("path", nargs="?", type=Path, default=DEFAULT_PROFILE)
        if name == "push":
            p.add_argument("--note", default="", help="what changed in this version")
        p.set_defaults(func=func)
    pull = prof.add_parser("pull", help="print the current profile")
    pull.set_defaults(func=_cmd_profile_pull)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    command: Callable[[argparse.Namespace], int] = args.func
    try:
        return command(args)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
