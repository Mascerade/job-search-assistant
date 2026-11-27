-- Computational research roles get their own track ("research"): Broad Institute's
-- Computational Associate, bioinformatics, and research assistant jobs built on programming.
-- Broad's Avature career site becomes a source.
alter type public.job_track add value if not exists 'research';
alter type public.job_source add value if not exists 'avature';

-- Default title keywords for the new track (editable on the Settings page). Generic research
-- titles ("Research Assistant I") are kept only when the description asks for programming;
-- that check is in pipeline/src/jobsearch/filters.py.
update public.settings
set data = jsonb_set(data, '{tracks,research}', jsonb_build_object(
  'enabled', true,
  'keywords', jsonb_build_array(
    'computational', 'bioinformatics', 'bioinformatician',
    'research assistant', 'research associate', 'research analyst'
  )))
where id = 1 and not coalesce(data -> 'tracks' ? 'research', false);

-- ingest_postings, plus: a job you added by hand ("Add job") that a source later lists at the
-- same URL is linked to that posting instead of being added a second time. The link only
-- records that the posting is still open (and lets close_missing_postings close it when it's
-- taken down); your title, notes, status, and pipeline progress stay as they are.
create or replace function public.ingest_postings(postings jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  p jsonb;
  existing public.jobs%rowtype;
  manual_id uuid;
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
      continue;
    end if;

    -- A job you added by hand: already linked to this posting, or at the same URL.
    select id into manual_id
      from public.jobs
      where source = 'manual'
        and ((source_board = p ->> 'source_board' and source_job_id = p ->> 'source_job_id')
          or (source_job_id is null
              and p ->> 'url' is not null
              and lower(rtrim(trim(url), '/')) = lower(rtrim(trim(p ->> 'url'), '/'))))
      order by created_at
      limit 1;

    if manual_id is not null then
      update public.jobs set
        last_seen_at  = now(),
        closed_at     = null,
        source_board  = p ->> 'source_board',
        source_job_id = p ->> 'source_job_id'
      where id = manual_id;
      updated := updated + 1;
      continue;
    end if;

    -- Same job already open from a *different* board (e.g. a job board re-posting
    -- an employer's listing). Within one board, different ids are different jobs:
    -- MIT posts several separate "Program/Project Coordinator" openings.
    if p ->> 'dedupe_key' is not null and exists (
      select 1 from public.jobs
      where dedupe_key = p ->> 'dedupe_key'
        and closed_at is null
        and source_board is distinct from p ->> 'source_board'
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
  end loop;

  return jsonb_build_object('inserted', inserted, 'updated', updated, 'duplicates', duplicates);
end;
$$;
