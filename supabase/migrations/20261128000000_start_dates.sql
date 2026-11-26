-- Start dates: when each job starts, read from the posting by the AI
-- (pipeline/src/jobsearch/timing.py; scoring reads it at the same time as the fit score).
--
-- Most postings don't say: the employer wants someone soon after the hire. Some name a window
-- ("Summer 2027 new-grad cohort"), and fixed-term university appointments end on a set date.
-- The website's Start column compares these with Settings → "Available from".

alter table public.jobs
  add column start_kind text check (start_kind in ('date', 'asap', 'unstated')),
  add column start_from date,
  add column start_to date,
  add column term_end date,
  add column start_note text check (length(start_note) <= 160),
  add constraint start_window check (start_from is null or start_to is null or start_from <= start_to);

comment on column public.jobs.start_kind is
  'date = the posting names a start window (start_from..start_to, either end open); '
  'asap = it says immediately; unstated = it does not say; null = not read yet';
comment on column public.jobs.term_end is 'Last day of a fixed-term appointment, if the posting gives one';

-- The one-off backfill (and the daily safety net) logs its own runs.
alter table public.runs drop constraint runs_kind_check;
alter table public.runs add constraint runs_kind_check
  check (kind in ('daily', 'local', 'scoring', 'timing', 'tailoring', 'tasks', 'digest', 'cleanup', 'on_demand'));

-- ---------------------------------------------------------------------------
-- record_timing: save start windows read from postings
-- ---------------------------------------------------------------------------
-- Each element: {job_id, start: {kind, earliest, latest, term_end, note}}.
create function public.record_timing(timings jsonb)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  t jsonb;
  saved integer := 0;
begin
  for t in select value from jsonb_array_elements(timings) loop
    update public.jobs set
      start_kind = t #>> '{start,kind}',
      start_from = (t #>> '{start,earliest}')::date,
      start_to   = (t #>> '{start,latest}')::date,
      term_end   = (t #>> '{start,term_end}')::date,
      start_note = nullif(left(t #>> '{start,note}', 160), '')
    where id = (t ->> 'job_id')::uuid;

    if found then
      saved := saved + 1;
    end if;
  end loop;
  return saved;
end;
$$;

revoke execute on function public.record_timing(jsonb) from public, anon, authenticated;
grant execute on function public.record_timing(jsonb) to service_role;

-- ---------------------------------------------------------------------------
-- record_scores: unchanged, plus the start window when the score carries one
-- ---------------------------------------------------------------------------
create or replace function public.record_scores(scores jsonb)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  s jsonb;
  saved integer := 0;
begin
  for s in select value from jsonb_array_elements(scores) loop
    insert into public.scores (job_id, score, reason, track, details, model, input_tokens, output_tokens, cost_usd)
    values (
      (s ->> 'job_id')::uuid,
      (s ->> 'score')::smallint,
      s ->> 'reason',
      (s ->> 'track')::public.job_track,
      coalesce(s -> 'details', '{}'::jsonb),
      s ->> 'model',
      (s ->> 'input_tokens')::integer,
      (s ->> 'output_tokens')::integer,
      (s ->> 'cost_usd')::numeric
    );

    update public.jobs j set
      fit_score = (s ->> 'score')::smallint,
      fit_reason = s ->> 'reason',
      track = coalesce((s ->> 'track')::public.job_track, j.track),
      tags = array(
        select distinct t from unnest(
          j.tags || array(select jsonb_array_elements_text(coalesce(s -> 'tags', '[]'::jsonb)))
        ) as t
        order by t
      ),
      pipeline_state = case
        when j.pipeline_state in ('new', 'scored', 'below_threshold')
          then (case when (s ->> 'keep')::boolean then 'scored' else 'below_threshold' end)::public.pipeline_state
        else j.pipeline_state
      end
    where j.id = (s ->> 'job_id')::uuid;

    if found then
      saved := saved + 1;
      if s ? 'start' then
        perform public.record_timing(jsonb_build_array(jsonb_build_object('job_id', s -> 'job_id', 'start', s -> 'start')));
      end if;
    end if;
  end loop;
  return saved;
end;
$$;

-- The 'future-start' tag is replaced by the start columns (the website shows the window itself).
-- Jobs that had it are read again by the backfill, since their start_kind is still null.
update public.jobs set tags = array_remove(tags, 'future-start') where 'future-start' = any(tags);
