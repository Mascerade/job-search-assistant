-- Milestone 2: daily job feed.

-- ---------------------------------------------------------------------------
-- Identity of a posting at its source
-- ---------------------------------------------------------------------------
-- A plain unique constraint (NULLs are distinct, so manual jobs never collide).
-- source_job_id is namespaced by board, e.g. "harvard:R0012345", because ids
-- from different Workday tenants can repeat.
drop index public.jobs_source_unique;
alter table public.jobs add constraint jobs_source_job_unique unique (source, source_job_id);

-- Which board a posting came from (e.g. "greenhouse:hubspot"), so postings that
-- disappear from that board can be marked closed.
alter table public.jobs add column source_board text;
create index jobs_open_by_board_idx on public.jobs (source_board) where closed_at is null;

-- ---------------------------------------------------------------------------
-- ingest_postings: save one day's postings in a single call
-- ---------------------------------------------------------------------------
-- New postings are inserted. Postings already in the table get their posting
-- fields refreshed, but never their application status, notes, contacts, or any
-- pipeline progress beyond the filter stage. A new posting whose dedupe_key
-- matches an open job from another source is skipped as a duplicate.
create function public.ingest_postings(postings jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  p jsonb;
  existing public.jobs%rowtype;
  inserted integer := 0;
  updated integer := 0;
  duplicates integer := 0;
begin
  for p in select value from jsonb_array_elements(postings) loop
    select * into existing
      from public.jobs
      where source = (p ->> 'source')::public.job_source
        and source_job_id = p ->> 'source_job_id';

    if found then
      update public.jobs j set
        last_seen_at    = now(),
        closed_at       = null,
        title           = p ->> 'title',
        url             = coalesce(p ->> 'url', j.url),
        location        = p ->> 'location',
        remote_type     = p ->> 'remote_type',
        employment_type = p ->> 'employment_type',
        salary_min      = (p ->> 'salary_min')::integer,
        salary_max      = (p ->> 'salary_max')::integer,
        description     = coalesce(p ->> 'description', j.description),
        posted_at       = coalesce((p ->> 'posted_at')::timestamptz, j.posted_at),
        dedupe_key      = p ->> 'dedupe_key',
        source_board    = p ->> 'source_board',
        track           = coalesce(j.track, (p ->> 'track')::public.job_track),
        tags            = array(
                            select distinct t from unnest(
                              j.tags || array(select jsonb_array_elements_text(coalesce(p -> 'tags', '[]'::jsonb)))
                            ) as t
                          ),
        -- Settings may have changed since last time: re-apply filters, but only
        -- to jobs that haven't moved past the filter stage.
        pipeline_state  = case when j.pipeline_state in ('new', 'filtered_out')
                               then (p ->> 'pipeline_state')::public.pipeline_state
                               else j.pipeline_state end,
        filter_reason   = case when j.pipeline_state in ('new', 'filtered_out')
                               then p ->> 'filter_reason'
                               else j.filter_reason end
      where j.id = existing.id;
      updated := updated + 1;
    else
      if p ->> 'dedupe_key' is not null and exists (
        select 1 from public.jobs
        where dedupe_key = p ->> 'dedupe_key' and closed_at is null
      ) then
        duplicates := duplicates + 1;
        continue;
      end if;

      insert into public.jobs (
        source, source_job_id, source_board, url, company, title, location, remote_type,
        employment_type, salary_min, salary_max, description, posted_at, dedupe_key,
        track, tags, pipeline_state, filter_reason
      ) values (
        (p ->> 'source')::public.job_source,
        p ->> 'source_job_id',
        p ->> 'source_board',
        p ->> 'url',
        p ->> 'company',
        p ->> 'title',
        p ->> 'location',
        p ->> 'remote_type',
        p ->> 'employment_type',
        (p ->> 'salary_min')::integer,
        (p ->> 'salary_max')::integer,
        p ->> 'description',
        (p ->> 'posted_at')::timestamptz,
        p ->> 'dedupe_key',
        (p ->> 'track')::public.job_track,
        array(select jsonb_array_elements_text(coalesce(p -> 'tags', '[]'::jsonb))),
        coalesce((p ->> 'pipeline_state')::public.pipeline_state, 'new'),
        p ->> 'filter_reason'
      );
      inserted := inserted + 1;
    end if;
  end loop;

  return jsonb_build_object('inserted', inserted, 'updated', updated, 'duplicates', duplicates);
end;
$$;

-- ---------------------------------------------------------------------------
-- close_missing_postings: mark postings closed when they leave their board
-- ---------------------------------------------------------------------------
-- Only call this after a *successful* full fetch of the board.
create function public.close_missing_postings(board text, seen_ids text[])
returns integer
language sql
security definer
set search_path = ''
as $$
  with closed as (
    update public.jobs
      set closed_at = now()
      where source_board = board
        and closed_at is null
        and not (source_job_id = any (seen_ids))
      returning 1
  )
  select count(*)::integer from closed;
$$;

-- Only the pipeline (service role) may call these.
revoke execute on function public.ingest_postings(jsonb) from public, anon, authenticated;
revoke execute on function public.close_missing_postings(text, text[]) from public, anon, authenticated;
grant execute on function public.ingest_postings(jsonb) to service_role;
grant execute on function public.close_missing_postings(text, text[]) to service_role;

-- ---------------------------------------------------------------------------
-- Broader default title keywords. Matching is word-based and order-free:
-- "program coordinator" also matches "Coordinator, Graduate Programs".
-- ---------------------------------------------------------------------------
update public.settings set data = jsonb_set(jsonb_set(jsonb_set(data,
  '{tracks,software,keywords}', jsonb_build_array(
    'software engineer', 'software developer', 'new grad', 'junior developer',
    'backend engineer', 'frontend engineer', 'full stack engineer', 'web developer',
    'application developer', 'programmer analyst', 'research software engineer',
    'machine learning engineer', 'ml engineer', 'ai engineer',
    'data engineer', 'data analyst', 'data scientist'
  )),
  '{tracks,program_admin,keywords}', jsonb_build_array(
    'program administrator', 'program coordinator', 'program manager', 'program specialist',
    'program assistant', 'program associate', 'program officer', 'project coordinator',
    'academic coordinator', 'administrative coordinator', 'department administrator',
    'research administrator'
  )),
  '{tracks,hybrid,keywords}', jsonb_build_array(
    'research computing', 'academic technology', 'educational technology',
    'instructional technology', 'learning technology', 'business systems analyst',
    'systems analyst', 'research data', 'data coordinator'
  ))
where id = 1;
