# Job Search Assistant

A private, single-user tool that finds Boston-area jobs every day, writes a tailored resume and
cover letter for each match, and tracks every application from "found" to "offer".

> Status: **Milestone 1 of 5** — the tracker website, database, login, and master profile work.
> The daily search, AI scoring, and document tailoring arrive in milestones 2–4.

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

## Tests

```bash
cd pipeline && uv run pytest && uv run ruff check .   # profile rules
cd web && npm run lint && npm run build               # types, lint, build
npx supabase test db                                  # row-level security + triggers (pgTAP)
```

CI runs all three on every push (`.github/workflows/ci.yml`).

## Milestones

1. ✅ Tracker + profile: schema, login, board, job detail, manual add, profile, settings
2. Daily job feed: Greenhouse / Lever / Ashby / Workday adapters, filters, `daily.yml` cron
3. AI scoring with Claude Haiku 5.5, spend cap, labeled eval set
4. Tailoring with Claude Opus 5.5, fact verification, DOCX/PDF rendering, approvals
5. Morning digest email, job-board APIs, HigherEdJobs, cleanup
