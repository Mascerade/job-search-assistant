# Job Search Assistant

A private, single-user tool that finds Boston-area jobs every day, writes a tailored resume and
cover letter for each match, and tracks every application from "found" to "offer".

> Status: **Milestone 2 of 5** — the tracker website, login, master profile, and the daily job feed
> (72 employer boards) work. AI scoring and document tailoring arrive in milestones 3–4.

## How it fits together

```
 GitHub Actions (daily cron, Python)          Supabase (free tier)              Vercel (free)
 ┌──────────────────────────────┐   writes    ┌──────────────────────┐  reads   ┌───────────────────┐
 │ fetch jobs → filter → score  │ ──────────► │ Postgres + Auth +     │ ◄──────► │ React website     │
 │ → tailor → render PDF/DOCX   │             │ Storage (row-level    │  writes  │ (tracker, review, │
 │ → email digest               │ ◄────────── │ security: owner only) │          │  approvals)       │
 └──────────────────────────────┘  tasks      └──────────────────────┘          └───────────────────┘
```

- **`pipeline/`** — Python. Everything that runs unattended: job sources, filters, Claude calls,
  document rendering. Uses the Supabase *secret* key (never shipped to the browser).
- **`web/`** — React + TypeScript + Vite + Tailwind + shadcn/ui. Talks to Supabase directly with
  the *publishable* key; row-level security makes every table readable only by the owner account.
- **`supabase/`** — the database schema (`migrations/`) and its security tests (`tests/`).
- **`design-system/`** — the UI/UX Pro Max design system the website is built against
  (see the "Project Adaptations" section of `MASTER.md`).
- **`private/`** and **`resumes/`** — personal data. **Gitignored**; never committed.

### Key ideas

- **One owner.** Sign-ups are disabled. `jobsearch owner create` registers the single account
  allowed in; every table's security policy checks `is_owner()`.
- **Master profile = the only source of facts.** Every fact has an id. Tailored resume bullets must
  cite fact ids; anything else becomes a *suggestion* that needs approval before a final PDF.
- **Status history is automatic.** A database trigger records every status change, and the browser
  can't write history (or rewrite a suggestion's text) directly.

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
"Show filtered out" on Today. Borderline cases are kept for the AI score in milestone 3.

## Deploy (all free tiers)

1. **GitHub** — the repo; `ci.yml` tests every push and `daily.yml` runs the job feed each morning.
2. **Supabase** — create a project (sign up with the same email you'll sign in with: the free
   email sender only delivers to your own Supabase team). Then, from the repo root:
   ```bash
   npx supabase login
   npx supabase link --project-ref <your-project-ref>
   npx supabase db push                     # applies supabase/migrations
   ```
   In the dashboard → Authentication: turn **off** "Allow new users to sign up", and set the
   Site URL to your Vercel URL (also add it under Redirect URLs).
3. **Pipeline secrets** — fill in `pipeline/.env.production` (gitignored), then:
   ```bash
   cd pipeline
   JOBSEARCH_ENV=production uv run jobsearch owner create --email you@example.com
   JOBSEARCH_ENV=production uv run jobsearch profile push --note "first version"
   cd .. && scripts/set-github-secrets.sh    # copies the two values into GitHub Actions secrets
   ```
4. **Vercel** — import the GitHub repo, set **Root Directory** to `web`, and add the environment
   variables `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` (the *publishable* key is safe
   in the browser; never the secret one). `web/vercel.json` handles page routing.
5. Run the feed once by hand: `gh workflow run daily.yml`, then open the site.

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
3. AI scoring with Claude Haiku 5.5, spend cap, labeled eval set
4. Tailoring with Claude Opus 5.5, fact verification, DOCX/PDF rendering, approvals
5. Morning digest email, job-board APIs, HigherEdJobs, cleanup
