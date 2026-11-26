-- Duplicates are only skipped across boards, never within one board.
create or replace function public.ingest_postings(postings jsonb)
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
    end if;
  end loop;

  return jsonb_build_object('inserted', inserted, 'updated', updated, 'duplicates', duplicates);
end;
$$;
