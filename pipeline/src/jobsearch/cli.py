"""Command-line entry point: `uv run jobsearch <command>`.

Milestone 1 commands:
  jobsearch owner create --email you@example.com   register the one account allowed to sign in
  jobsearch profile validate [PATH]                check a profile YAML file
  jobsearch profile push [PATH] --note "..."       upload it as a new profile version
  jobsearch profile pull                           print the current profile as YAML
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from .config import REPO_DIR, ConfigError
from .profile import load_profile, profile_from_data

DEFAULT_PROFILE = REPO_DIR / "private" / "profile.yaml"


def _cmd_owner_create(args: argparse.Namespace) -> int:
    from . import db

    user_id, created = db.ensure_owner(args.email)
    verb = "Created" if created else "Found existing"
    print(f"{verb} account {args.email} ({user_id}) and registered it as the site owner.")
    return 0


def _load_or_report(path: Path):
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
    print(f"# version {row['version']} ({row['created_at']}) {row['note']}".rstrip())
    # Postgres jsonb doesn't keep key order; re-dump through the model for a readable layout.
    data = profile_from_data(row["data"]).model_dump(mode="json", exclude_defaults=True)
    print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobsearch", description="Job search assistant pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

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
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
