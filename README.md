# Job Search Assistant

A private, single-user tool that finds Boston-area jobs every day, writes a tailored resume and
cover letter for each match, and tracks every application from "found" to "offer".

> Status: **All 6 milestones built.** Daily job feed (72 employer boards + Adzuna), AI fit scoring,
> tailored resumes + cover letters with an approval flow, a morning digest email, and apply assist
> (Claude fills an application in your Chrome and stops before Submit).

## How it fits together

```
  GitHub Actions (cloud, ~5:15am)          Supabase (free tier)                 Vercel (free)
  ┌───────────────────────────┐  writes   ┌─────────────────────────┐  reads   ┌──────────────────┐
  │ fetch boards + Adzuna →   │ ────────► │ Postgres + Auth +        │ ◄──────► │ React website    │
  │ filter → cleanup          │           │ Storage (owner-only RLS) │  writes  │ tracker, review, │
  └───────────────────────────┘           │                          │          │ downloads        │
  Kojo's Mac (LaunchAgents)               │                          │ (tasks)  │                  │
  ┌───────────────────────────┐  reads/   │                          │          └──────────────────┘
  │ 7:30am: Workday boards →  │  writes   │                          │
  │ score (Sonnet) → tailor   │ ◄───────► │                          │
  │ (Opus) → check → PDFs →   │           └─────────────────────────┘
  │ digest email (Gmail)      │
  │ listener: button presses  │  AI = local Claude Code (`claude -p`) on Kojo's Claude plan
  │ via Realtime (websocket)  │
  └───────────────────────────┘
```

- **`pipeline/`** — Python. Job sources, filters, AI scoring and tailoring (through the local
  Claude Code CLI), fact checks, Word/PDF rendering (LibreOffice), uploads. Uses the Supabase
  *secret* key, which never reaches the browser.
- **`web/`** — React + TypeScript + Vite + Tailwind + shadcn/ui. Talks to Supabase directly with
  the *publishable* key; row-level security limits every table to the owner account.
- **`supabase/`** — schema (`migrations/`) and pgTAP security tests (`tests/`).
- **`design-system/`** — the design system the website follows (Notion-inspired restyle, approved from
  Figma mockups; see the last section of `MASTER.md`).
- **`private/`** and **`resumes/`** — personal data (master profile, eval labels). **Gitignored.**

### Key ideas

- **One owner.** Sign-ups are disabled; every table's policy checks `is_owner()`.
- **Master profile = the only source of facts.** Tailored bullets cite fact ids. Code checks
  (fact ids, numbers, skills, placeholders) and a second model pass turn anything unsupported
  into a *suggestion* you approve, edit, or reject before the PDFs are built.
- **Workday runs on the Mac.** Workday rate-limits cloud servers, so `daily.yml` uses
  `--where cloud` and the Mac's `jobsearch local-daily` fetches Workday boards.
- **Status history is automatic.** A trigger records every status change.
- **Insights.** `/insights` charts the search: the funnel from found to offer, % applied, role
  types, sources, work setup, staffing-agency share, when jobs start (against "Available from"),
  matches per day, fit scores, top employers.
  Definitions live in `web/src/lib/insights.ts` (Today's headline numbers use the same ones).
- **Timing focus.** Until a date in Settings (default March 1, 2027) the daily 20 documents go to
  software, then university tech, then program admin: admin roles usually hire weeks before the
  start date, and the start has to be after graduation. Postings whose start window reaches
  "Available from" in Settings (a "June 2027 new grads" program) jump the line; staffing agencies
  always go last (`priority.py`).
- **Start dates.** While scoring, the AI also reads when each job starts: a stated window, "immediately",
  or not stated (most postings), plus the end date of fixed-term appointments (`timing.py`). Timing
  details sit late in long postings, so scoring adds those sentences after its usual excerpt.
  `uv run jobsearch timing` fills in jobs scored before this existed; the Mac's daily run calls it
  too, and it makes no AI call when nothing is missing.

## Run it locally

Prerequisites: Docker, Node 24+, [uv](https://docs.astral.sh/uv/).

```bash
# 1. Database (first run downloads the Supabase images)
npx supabase start -x imgproxy,vector,logflare,supavisor,edge-runtime
npx supabase status -o env        # shows API_URL, PUBLISHABLE_KEY, SECRET_KEY

# 2. Pipeline: register yourself and upload your profile
cp pipeline/.env.example pipeline/.env      # fill in SUPABASE_SECRET_KEY
cd pipeline
uv run jobsearch owner create --email you@example.com
uv run jobsearch profile validate           # checks private/profile.yaml
uv run jobsearch profile push --note "first version"
cd ..

# 3. Website
cp web/.env.example web/.env.local          # fill in VITE_SUPABASE_PUBLISHABLE_KEY
cd web && npm install && npm run dev        # http://localhost:5173
```

Locally, sign-in emails don't really send: open the Mailpit inbox at http://127.0.0.1:54324 to
click your magic link.

## The daily job feed

`config/sources.yaml` lists the employer boards (universities, hospitals, tech companies) and which
careers platform each uses. Every morning `.github/workflows/daily.yml` runs:

```bash
cd pipeline
uv run jobsearch daily --dry-run   # fetch + filter, print what it would keep, save nothing
uv run jobsearch daily             # fetch, filter, save to Supabase, close postings that disappeared
```

Filtering is cheap and deterministic (no AI): title must match a track's keywords and not be senior
or part-time; location must be one of your towns, US-remote, or hybrid; obvious mismatches in the
description (5+ years required, security clearance) are dropped with a reason you can see under
"Show filtered out" on Today. Borderline cases are kept for the AI score.

**Adzuna** (a job-board aggregator, free key at developer.adzuna.com) catches employers that aren't
in `sources.yaml`. It searches job titles around Boston from the last 14 days. Its copies of jobs
from employers we already read directly are skipped (`aliases:` in `sources.yaml` covers other
names, like "Massachusetts Institute of Technology" for MIT). Adzuna only shares a snippet of each
description, so those jobs carry a "Short description" tag; open the link for the full posting.

**Staffing agencies** (companies that post jobs for other employers, often as contracts, with the
real employer hidden) get a "Staffing agency" tag. The daily tailoring does every direct-employer
match first and only then agency jobs, so the 20 daily documents go where a tailored cover letter
counts most. The list is `config/staffing_agencies.yaml`; names with "staffing"/"recruiting" and
Adzuna postings written like "Our client is seeking…" are caught automatically.

**Cleanup** runs after the feed (`uv run jobsearch cleanup --dry-run` shows what it would do):
postings that closed 30+ days ago and Adzuna postings 45+ days old are deleted if you never
touched them (status still New / Docs ready / Not interested, no notes or contacts; hand-added
jobs are never deleted), and files for jobs rejected, withdrawn, or not interested for 60+ days
are removed (the job and its history stay). This keeps Storage under the free 1 GB and the
website under its 1,000-job load. The workflow also commits `.github/heartbeat` when the repo has
had no commits for 50 days, because GitHub pauses schedules in quiet public repos after 60.

## Deploy (all free tiers)

1. **GitHub** — the repo; `ci.yml` tests every push and `daily.yml` runs the job feed each morning.
2. **Supabase** — create a project (sign up with the same email you'll sign in with: the free
   email sender only delivers to your own Supabase team). Then, from the repo root:
   ```bash
   npx supabase login
   npx supabase link --project-ref <your-project-ref>
   npx supabase db push --remote            # applies supabase/migrations (without --remote it targets the local DB)
   ```
   In the dashboard → Authentication: turn **off** "Allow new users to sign up", and set the
   Site URL to your Vercel URL (also add it under Redirect URLs).
3. **Pipeline secrets** — fill in `pipeline/.env.production` (gitignored), then:
   ```bash
   cd pipeline
   JOBSEARCH_ENV=production uv run jobsearch owner create --email you@example.com
   JOBSEARCH_ENV=production uv run jobsearch profile push --note "first version"
   cd .. && scripts/set-github-secrets.sh    # copies the Supabase (and Adzuna) values into GitHub Actions secrets
   ```
4. **Vercel** — import the GitHub repo, set **Root Directory** to `web`, and add the environment
   variables `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` (the *publishable* key is safe
   in the browser; never the secret one). `web/vercel.json` handles page routing.
5. Run the feed once by hand: `gh workflow run daily.yml`, then open the site.

## The Mac's jobs

```bash
cd pipeline
uv run jobsearch schedule install      # daily 7:30am job + an always-on request listener (LaunchAgents)
uv run jobsearch schedule status       # loaded? last exit code? recent log lines
uv run jobsearch local-daily           # what the daily job runs: Workday → score → tasks → tailor (20/day) → digest
uv run jobsearch tailor --job <id>     # tailor one job now
uv run jobsearch listen                # handle website button presses as they happen (Supabase Realtime)
uv run jobsearch eval report           # compare AI scores with your labels (private/eval/)
uv run jobsearch digest --dry-run      # print the morning email and save output/digest-preview.html
```

### Morning digest

At the end of `local-daily`, the Mac emails you (from your Gmail, to your Gmail) what changed since
the last digest: new matches, documents waiting for review, documents ready to download,
applications in Applied for 14+ days, and problems (failed runs, boards that couldn't be fetched,
an expiring Claude sign-in, the usage cap). No news means no email. Setup: turn on 2-Step
Verification for the Google account, create an app password at myaccount.google.com/apppasswords,
and add `GMAIL_ADDRESS` and `GMAIL_APP_PASSWORD` to `pipeline/.env.production` (optional:
`DIGEST_TO` to send elsewhere, `SITE_URL` for the links).

## Applying with Claude (apply assist)

On a job's page, **Help me apply** shows whether it's ready (final documents, no pending
suggestions, posting open) and the command to type in Claude Code on the Mac:

```
/apply 3f9a2c1e        # the job's id from the page, or words from the title: /apply formlabs embedded
```

1. `jobsearch apply prepare` checks the job and saves its final resume + cover letter and a
   `packet.json` into `private/applications/<job>/` (gitignored; the lasting record of what was sent).
2. Claude opens the application form in a new Chrome tab and fills it, page by page:
   - your profile and the **Application answers** on the Profile page;
   - the uploaded documents;
   - drafts of essay answers, which you approve one by one in chat.
3. It **stops before Submit** and shows a summary table and a screenshot. You submit, or reply
   `submit`.
4. `jobsearch apply done` marks the job Applied and adds a note (documents, essays). Demographic
   answers are never recorded.

**What Claude never does:** type passwords or create accounts (on Workday, you sign in first),
solve CAPTCHAs, enter ID numbers, tick "I certify" boxes, or submit without your OK. The rules live
in `.claude/skills/apply/SKILL.md`. `scripts/apply-sandbox/` is a fake form for testing the
browser tools.

## Tests

```bash
cd pipeline && uv run pytest && uv run ruff check . && uv run mypy   # filters, adapters, profile; strict types
cd web && npm run lint && npm run build               # types, lint, build
npx supabase test db                                  # row-level security + triggers (pgTAP)
```

CI runs all three on every push (`.github/workflows/ci.yml`).

## Milestones

1. ✅ Tracker + profile: schema, login, board, job detail, manual add, profile, settings
2. ✅ Daily job feed: 9 careers platforms, 72 boards, filters, `daily.yml` cron
3. ✅ AI fit scoring with Claude Sonnet via local Claude Code; threshold 50 from a labeled eval set
4. ✅ Tailored resume + cover letter with Claude Opus; fact checks; suggestions to approve/edit; Word + PDF
5. ✅ Morning digest email (Gmail), Adzuna job-board search, cleanup, schedule heartbeat
   (HigherEdJobs blocks automated access; add its jobs with "Add job")
6. ✅ Apply assist: `/apply` in Claude Code fills the application in Chrome from your profile, saved answers,
   and tailored documents, then stops before Submit for your review
