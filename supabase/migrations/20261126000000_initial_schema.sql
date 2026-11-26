-- Job Search Assistant — initial schema
--
-- Security model: this is a single-user app. Exactly one auth user is registered in
-- `app_owner`, and every table's row-level-security policy checks `is_owner()`.
-- The Python pipeline uses the service-role key, which bypasses RLS, so tables don't
-- need per-row owner columns.

-- ---------------------------------------------------------------------------
-- Owner
-- ---------------------------------------------------------------------------
create table public.app_owner (
  user_id uuid primary key references auth.users (id) on delete cascade,
  created_at timestamptz not null default now()
);
alter table public.app_owner enable row level security;

create function public.is_owner()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (select 1 from public.app_owner where user_id = auth.uid());
$$;

create policy "owner can read own row" on public.app_owner
  for select to authenticated using (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
create type public.application_status as enum (
  'new', 'docs_ready', 'applied', 'interviewing',
  'offer', 'rejected', 'withdrawn', 'not_interested'
);

-- Where a job is in the automated pipeline (separate from the application status above).
create type public.pipeline_state as enum (
  'new', 'filtered_out', 'scored', 'below_threshold',
  'tailoring', 'needs_approval', 'ready', 'error'
);

create type public.job_track as enum ('software', 'program_admin', 'hybrid');

create type public.job_source as enum (
  'manual', 'greenhouse', 'lever', 'ashby', 'workday',
  'adzuna', 'jsearch', 'higheredjobs', 'other'
);

-- ---------------------------------------------------------------------------
-- Shared trigger: keep updated_at current
-- ---------------------------------------------------------------------------
create function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- Jobs: one row per posting, plus my application to it (1:1)
-- ---------------------------------------------------------------------------
create table public.jobs (
  id uuid primary key default gen_random_uuid(),

  -- Posting (written by the pipeline or the "Add job" form)
  source public.job_source not null default 'manual',
  source_job_id text,
  url text,
  company text not null check (length(trim(company)) > 0),
  title text not null check (length(trim(title)) > 0),
  location text,
  remote_type text check (remote_type in ('onsite', 'hybrid', 'remote')),
  employment_type text,
  salary_min integer check (salary_min >= 0),
  salary_max integer check (salary_max >= 0),
  description text,
  posted_at timestamptz,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  closed_at timestamptz,
  dedupe_key text,
  track public.job_track,
  tags text[] not null default '{}',

  -- Pipeline
  pipeline_state public.pipeline_state not null default 'new',
  filter_reason text,
  fit_score smallint check (fit_score between 0 and 100),
  fit_reason text,

  -- My application (edited on the website)
  status public.application_status not null default 'new',
  applied_at timestamptz,
  notes text not null default '',
  contacts jsonb not null default '[]'::jsonb check (jsonb_typeof(contacts) = 'array'),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint salary_range check (salary_min is null or salary_max is null or salary_min <= salary_max)
);

create unique index jobs_source_unique on public.jobs (source, source_job_id)
  where source_job_id is not null;
create index jobs_status_idx on public.jobs (status);
create index jobs_pipeline_state_idx on public.jobs (pipeline_state);
create index jobs_first_seen_idx on public.jobs (first_seen_at desc);
create index jobs_dedupe_key_idx on public.jobs (dedupe_key);

create trigger jobs_set_updated_at
  before update on public.jobs
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Status history: filled automatically by a trigger, never written by clients
-- ---------------------------------------------------------------------------
create table public.status_history (
  id bigint generated always as identity primary key,
  job_id uuid not null references public.jobs (id) on delete cascade,
  from_status public.application_status,
  to_status public.application_status not null,
  changed_at timestamptz not null default now()
);
create index status_history_job_idx on public.status_history (job_id, changed_at desc);

create function public.track_status_change()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' then
    insert into public.status_history (job_id, from_status, to_status)
      values (new.id, null, new.status);
  elsif new.status is distinct from old.status then
    insert into public.status_history (job_id, from_status, to_status)
      values (new.id, old.status, new.status);
  end if;
  return new;
end;
$$;

-- Stamp applied_at the first time a job moves to "applied".
create function public.stamp_applied_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if new.status = 'applied' and new.applied_at is null then
    new.applied_at = now();
  end if;
  return new;
end;
$$;

create trigger jobs_stamp_applied_at
  before insert or update of status on public.jobs
  for each row execute function public.stamp_applied_at();

create trigger jobs_track_status
  after insert or update of status on public.jobs
  for each row execute function public.track_status_change();

-- ---------------------------------------------------------------------------
-- Fit scores (history; the latest is copied onto jobs.fit_score / fit_reason)
-- ---------------------------------------------------------------------------
create table public.scores (
  id bigint generated always as identity primary key,
  job_id uuid not null references public.jobs (id) on delete cascade,
  score smallint not null check (score between 0 and 100),
  reason text not null,
  track public.job_track,
  details jsonb not null default '{}'::jsonb,
  model text not null,
  input_tokens integer,
  output_tokens integer,
  cost_usd numeric(10, 5),
  created_at timestamptz not null default now()
);
create index scores_job_idx on public.scores (job_id, created_at desc);

-- ---------------------------------------------------------------------------
-- Tailored documents and the suggestions inside them
-- ---------------------------------------------------------------------------
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs (id) on delete cascade,
  kind text not null check (kind in ('resume', 'cover_letter')),
  version integer not null default 1 check (version > 0),
  template text not null,
  content jsonb not null,
  docx_path text,
  pdf_path text,
  state text not null default 'needs_approval'
    check (state in ('needs_approval', 'final', 'error')),
  model text,
  cost_usd numeric(10, 5),
  created_at timestamptz not null default now(),
  unique (job_id, kind, version)
);
create index documents_job_idx on public.documents (job_id, kind, version desc);

create table public.suggestions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents (id) on delete cascade,
  path text not null,               -- where in the document, e.g. "experience.0.bullets.2"
  original_text text,               -- null when the suggestion is a brand-new bullet
  suggested_text text not null,
  rationale text not null,
  decision text not null default 'pending'
    check (decision in ('pending', 'approved', 'rejected')),
  decided_at timestamptz,
  created_at timestamptz not null default now()
);
create index suggestions_document_idx on public.suggestions (document_id);

-- ---------------------------------------------------------------------------
-- Master profile (every save is a new version; the highest version is current)
-- ---------------------------------------------------------------------------
create table public.profile_versions (
  version integer generated always as identity primary key,
  data jsonb not null check (jsonb_typeof(data) = 'object'),
  note text not null default '',
  created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Settings (single row)
-- ---------------------------------------------------------------------------
create table public.settings (
  id smallint primary key default 1 check (id = 1),
  data jsonb not null default '{}'::jsonb check (jsonb_typeof(data) = 'object'),
  updated_at timestamptz not null default now()
);
create trigger settings_set_updated_at
  before update on public.settings
  for each row execute function public.set_updated_at();

insert into public.settings (id, data) values (1, jsonb_build_object(
  'fit_threshold', 70,
  'monthly_spend_cap_usd', 40,
  'tracks', jsonb_build_object(
    'software', jsonb_build_object(
      'enabled', true,
      'keywords', jsonb_build_array(
        'software engineer', 'software developer', 'new grad', 'junior developer',
        'machine learning engineer', 'ml engineer', 'ai engineer', 'data engineer', 'data analyst'
      )
    ),
    'program_admin', jsonb_build_object(
      'enabled', true,
      'keywords', jsonb_build_array(
        'program administrator', 'program coordinator', 'program manager',
        'program specialist', 'academic coordinator', 'administrative coordinator'
      )
    ),
    'hybrid', jsonb_build_object(
      'enabled', true,
      'keywords', jsonb_build_array(
        'research computing', 'academic technology', 'educational technology',
        'business systems analyst', 'research data'
      )
    )
  ),
  'locations', jsonb_build_object(
    'include_remote_us', true,
    'include_hybrid', true,
    'towns', jsonb_build_array(
      'Boston', 'Cambridge', 'Somerville', 'Brookline', 'Newton', 'Waltham', 'Watertown',
      'Medford', 'Malden', 'Quincy', 'Arlington', 'Belmont', 'Lexington', 'Burlington',
      'Needham', 'Wellesley', 'Framingham', 'Woburn', 'Chelsea', 'Everett', 'Revere',
      'Dedham', 'Milton', 'Braintree', 'Salem', 'Lynn', 'Lowell', 'Worcester'
    )
  ),
  'experience_max_years', 2,
  'full_time_only', true,
  'exclude_clearance', true
));

-- ---------------------------------------------------------------------------
-- Pipeline runs and on-demand tasks
-- ---------------------------------------------------------------------------
create table public.runs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('daily', 'on_demand')),
  status text not null default 'running' check (status in ('running', 'succeeded', 'failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  counts jsonb not null default '{}'::jsonb,
  cost_usd numeric(10, 5) not null default 0,
  error text
);
create index runs_started_idx on public.runs (started_at desc);

-- A task is a button press on the website ("Render", "Regenerate", "Add by link").
-- The website inserts a row; the pipeline updates `step` as it works, and the
-- website shows progress live via Realtime.
create table public.tasks (
  id uuid primary key default gen_random_uuid(),
  job_id uuid references public.jobs (id) on delete cascade,
  kind text not null check (kind in ('ingest', 'tailor', 'render', 'regenerate')),
  input jsonb not null default '{}'::jsonb,
  step text not null default 'queued'
    check (step in ('queued', 'writing', 'rendering', 'ready', 'error')),
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index tasks_job_idx on public.tasks (job_id, created_at desc);
create trigger tasks_set_updated_at
  before update on public.tasks
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Row-level security: everything is owner-only
-- ---------------------------------------------------------------------------
alter table public.jobs enable row level security;
alter table public.status_history enable row level security;
alter table public.scores enable row level security;
alter table public.documents enable row level security;
alter table public.suggestions enable row level security;
alter table public.profile_versions enable row level security;
alter table public.settings enable row level security;
alter table public.runs enable row level security;
alter table public.tasks enable row level security;

-- Full access for the owner
create policy "owner full access" on public.jobs
  for all to authenticated using (public.is_owner()) with check (public.is_owner());
create policy "owner full access" on public.profile_versions
  for all to authenticated using (public.is_owner()) with check (public.is_owner());

-- Read + limited writes
create policy "owner read" on public.status_history
  for select to authenticated using (public.is_owner());
create policy "owner read" on public.scores
  for select to authenticated using (public.is_owner());
create policy "owner read" on public.documents
  for select to authenticated using (public.is_owner());
create policy "owner read" on public.runs
  for select to authenticated using (public.is_owner());

create policy "owner read" on public.suggestions
  for select to authenticated using (public.is_owner());
create policy "owner decides" on public.suggestions
  for update to authenticated using (public.is_owner()) with check (public.is_owner());

create policy "owner read" on public.settings
  for select to authenticated using (public.is_owner());
create policy "owner update" on public.settings
  for update to authenticated using (public.is_owner()) with check (public.is_owner());

create policy "owner read" on public.tasks
  for select to authenticated using (public.is_owner());
create policy "owner create" on public.tasks
  for insert to authenticated with check (public.is_owner());

-- The website may only change a suggestion's decision, not its content.
revoke update on public.suggestions from authenticated;
grant update (decision, decided_at) on public.suggestions to authenticated;

-- ---------------------------------------------------------------------------
-- Storage: private bucket for generated .docx / .pdf files
-- ---------------------------------------------------------------------------
insert into storage.buckets (id, name, public)
  values ('documents', 'documents', false)
  on conflict (id) do nothing;

create policy "owner reads documents" on storage.objects
  for select to authenticated
  using (bucket_id = 'documents' and public.is_owner());

-- ---------------------------------------------------------------------------
-- Realtime: the website listens for task progress and job changes
-- ---------------------------------------------------------------------------
alter publication supabase_realtime add table public.tasks;
alter publication supabase_realtime add table public.jobs;
