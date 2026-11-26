"""Command-line entry point: `uv run jobsearch <command>`.

Commands:
  jobsearch daily [--dry-run] [--where cloud|local] fetch job boards, filter, and save
  jobsearch score [--dry-run] [--limit N]          AI fit scores for jobs waiting to be scored
  jobsearch local-daily                            the Mac's daily job: Workday boards, then scoring
  jobsearch eval export | report                   evaluation set for the fit scores
  jobsearch schedule install|run-now|status|uninstall   the Mac's daily LaunchAgent
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
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from pydantic import ValidationError

from .config import REPO_DIR, ConfigError
from .llm import AuthExpiredError
from .profile import Profile, load_profile, profile_from_data

if TYPE_CHECKING:
    from .scoring import ScoringSummary

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

    summary = run_daily(dry_run=args.dry_run, only=args.only or None, where=args.where)
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


def _warn_if_signin_expiring(expires: datetime | None) -> None:
    if expires is None:
        return
    days = (expires - datetime.now(UTC)).days
    if days <= 10:
        print(
            f"⚠ Claude Code sign-in ends in {max(days, 0)} days ({expires:%b %d}). Run `claude` and /login, "
            "or set CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token`.",
            file=sys.stderr,
        )


def _print_scoring(s: ScoringSummary, *, show: int = 0) -> None:
    if s.skipped_reason:
        print(f"Scoring skipped: {s.skipped_reason}")
        return
    print(
        f"Scored {s.scored}: {s.kept} matches, {s.below} below threshold, {s.failed} failed "
        f"(estimated API value ${s.cost_usd:.3f}; free on your Claude plan)"
    )
    for err in s.errors:
        print(f"  ! {err}", file=sys.stderr)
    _warn_if_signin_expiring(s.credential_expires_at)
    for job, item in sorted(s.items, key=lambda ji: -ji[1].score)[:show]:
        print(f"  {item.score:>3}  [{item.track}] {job.title} — {job.company}\n       {item.reason}")


def _cmd_score(args: argparse.Namespace) -> int:
    from .scoring import run_scoring

    s = run_scoring(limit=args.limit, model=args.model, dry_run=args.dry_run)
    _print_scoring(s, show=args.show if args.dry_run else 0)
    return 1 if s.failed and not s.scored else 0


def _cmd_local_daily(args: argparse.Namespace) -> int:
    from .daily import run_daily
    from .scoring import run_scoring

    feed = run_daily(where="local", kind="local")
    c = feed.counts
    print(f"Workday boards: {c['boards_ok']} ok, {c['boards_failed']} failed | kept {c['kept']} | "
          f"saved {c['inserted']} new, {c['updated']} updated, {c['closed']} closed")  # fmt: skip
    for err in feed.errors:
        print(f"  ! {err}", file=sys.stderr)
    s = run_scoring(model=args.model)
    _print_scoring(s)
    return 1 if (c["boards_ok"] == 0 and feed.errors) or (s.failed and not s.scored) else 0


def _cmd_eval_export(args: argparse.Namespace) -> int:
    from . import db
    from .evaluation import LABELS_FILE, sample, to_items, write_labels_file

    if LABELS_FILE.exists() and not args.force:
        print(f"{LABELS_FILE} already exists (it may have your labels). Use --force to replace it.")
        return 1
    picked = sample(db.eval_candidates(), args.n)
    write_labels_file(to_items(picked, db.job_urls([j.id for j in picked])))
    print(
        f"Wrote {len(picked)} jobs to {LABELS_FILE}.\n"
        "Label each yes / maybe / no, then run: jobsearch eval report"
    )
    return 0


def _cmd_eval_report(args: argparse.Namespace) -> int:
    from . import db
    from .evaluation import metrics, read_labels_file, suggest_threshold
    from .llm import ClaudeCode
    from .scoring import BATCH_SIZE, ScoreItem, score_batch

    labeled = [i for i in read_labels_file() if i.label]
    if len(labeled) < 10:
        print(f"Only {len(labeled)} jobs are labeled; label at least 10 (ideally all) first.")
        return 1
    settings = db.load_settings()
    row = db.latest_profile()
    if row is None:
        print("No master profile uploaded yet.")
        return 1
    profile = Profile.model_validate(row.data)
    jobs = db.jobs_by_ids([i.job_id for i in labeled])
    engine = ClaudeCode(model=args.model)
    scores: dict[str, ScoreItem] = {}
    for i in range(0, len(jobs), BATCH_SIZE):
        items, _ = score_batch(engine, jobs[i : i + BATCH_SIZE], profile, settings)
        scores.update({it.job_id: it for it in items})
    pairs = [(i.label, scores[i.job_id].score) for i in labeled if i.label and i.job_id in scores]
    rows = metrics(pairs)
    counts = {k: sum(1 for i in labeled if i.label == k) for k in ("yes", "maybe", "no")}
    print(f"{len(pairs)} labeled jobs scored with {args.model}: {counts}\n")
    print("threshold  shown  precision  recall(yes+maybe)  recall(yes)")
    for r in rows:
        print(
            f"{r.threshold:>9}  {r.shown:>5}  {r.precision:>9.0%}  {r.recall:>17.0%}  {r.recall_yes:>11.0%}"
        )
    t = suggest_threshold(rows)
    print(f"\nSuggested threshold: {t} (current: {settings.fit_threshold}). Shows ≥90% of your 'yes' jobs.")
    print("\nDisagreements at that threshold:")
    for item in labeled:
        s = scores.get(item.job_id)
        if s is None:
            continue
        miss = item.label == "yes" and s.score < t
        noise = item.label == "no" and s.score >= t
        if miss or noise:
            kind = "MISSED (you: yes)" if miss else "NOISE (you: no)"
            note = f" | your note: {item.note}" if item.note else ""
            print(f"  {kind:<18} {s.score:>3}  {item.title} — {item.company}\n{'':22}{s.reason}{note}")
    return 0


def _cmd_schedule(args: argparse.Namespace) -> int:
    from . import schedule

    if args.action == "install":
        hour, minute = (int(x) for x in args.at.split(":"))
        path = schedule.install(hour, minute)
        print(
            f"Installed {path}\n"
            f"Runs `jobsearch local-daily` every day at {hour:02d}:{minute:02d} (or on wake)."
        )
    elif args.action == "run-now":
        schedule.run_now()
        print(f"Started. Follow along with: tail -f {schedule.LOG}")
    elif args.action == "uninstall":
        print("Removed." if schedule.uninstall() else "It wasn't installed.")
    else:
        print(schedule.status())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jobsearch", description="Job search assistant pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    daily = sub.add_parser("daily", help="run the daily job feed")
    daily.add_argument("--dry-run", action="store_true", help="fetch and filter, but write nothing")
    daily.add_argument("--only", nargs="*", help="limit to boards by token, key, or company name")
    daily.add_argument(
        "--where",
        choices=["all", "cloud", "local"],
        default="all",
        help="cloud = boards GitHub Actions can reach; local = Workday boards (run on your Mac)",
    )
    daily.add_argument("--show", type=int, default=60, help="how many kept jobs to list in a dry run")
    daily.set_defaults(func=_cmd_daily)

    score = sub.add_parser("score", help="AI fit scores for jobs waiting to be scored")
    score.add_argument("--dry-run", action="store_true", help="score and print, but save nothing")
    score.add_argument("--limit", type=int, help="score at most this many jobs")
    score.add_argument("--model", default="sonnet", help="Claude model alias (default: sonnet)")
    score.add_argument("--show", type=int, default=20, help="how many results to print in a dry run")
    score.set_defaults(func=_cmd_score)

    local = sub.add_parser("local-daily", help="the Mac's daily job: Workday boards, then scoring")
    local.add_argument("--model", default="sonnet", help="Claude model alias for scoring")
    local.set_defaults(func=_cmd_local_daily)

    sch = sub.add_parser("schedule", help="the Mac's daily LaunchAgent")
    sch.add_argument("action", choices=["install", "run-now", "status", "uninstall"])
    sch.add_argument("--at", default="07:30", help="daily time for install, HH:MM (default 07:30)")
    sch.set_defaults(func=_cmd_schedule)

    ev = sub.add_parser("eval", help="evaluation set for the fit scores").add_subparsers(
        dest="action", required=True
    )
    exp = ev.add_parser("export", help="write ~40 jobs to private/eval/scoring_labels.yaml for labeling")
    exp.add_argument("--n", type=int, default=40)
    exp.add_argument("--force", action="store_true", help="replace an existing labels file")
    exp.set_defaults(func=_cmd_eval_export)
    rep = ev.add_parser("report", help="score the labeled jobs and compare with your labels")
    rep.add_argument("--model", default="sonnet")
    rep.set_defaults(func=_cmd_eval_report)

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
    except AuthExpiredError as e:
        print(
            "Claude Code isn't signed in anymore, so AI steps can't run.\n"
            "Fix: run `claude` and type /login — or create a one-year token with `claude setup-token`\n"
            f"and put it in pipeline/.env.production as CLAUDE_CODE_OAUTH_TOKEN.\n({e})",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    sys.exit(main())
