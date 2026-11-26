-- Milestone 3: AI fit scoring.

-- Run kinds: the cloud feed ('daily'), the Mac's Workday feed ('local'), and scoring.
alter table public.runs drop constraint runs_kind_check;
alter table public.runs add constraint runs_kind_check
  check (kind in ('daily', 'local', 'scoring', 'on_demand'));

-- ---------------------------------------------------------------------------
-- record_scores: save a batch of fit scores atomically
-- ---------------------------------------------------------------------------
-- Each element: {job_id, score, reason, track, keep, tags[], details{}, model,
-- input_tokens, output_tokens, cost_usd}. `keep` is decided by the pipeline from
-- the fit threshold. Jobs already past scoring (tailoring, approved, ...) keep
-- their pipeline state; their score and reason are still refreshed.
create function public.record_scores(scores jsonb)
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
    end if;
  end loop;
  return saved;
end;
$$;

revoke execute on function public.record_scores(jsonb) from public, anon, authenticated;
grant execute on function public.record_scores(jsonb) to service_role;
