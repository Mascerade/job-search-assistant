-- 1. Suggestions on replaced document versions are closed as 'superseded'.
--    Regenerating a job's documents used to leave the old version's suggestions 'pending'
--    forever, which inflated the "waiting for review" counts.
-- 2. The 'immediate-start' tag is dropped: the scorer set it on nearly every posting (anything
--    without a named future start), so it said nothing. Scoring now tags the rare opposite,
--    'future-start' (e.g. a 2027 new-grad program), which the tailoring order puts first.

alter table public.suggestions drop constraint suggestions_decision_check;
alter table public.suggestions add constraint suggestions_decision_check
  check (decision in ('pending', 'approved', 'rejected', 'superseded'));

create or replace function public.save_tailored(job uuid, payload jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  kinds text[] := array['resume', 'cover_letter'];
  k text;
  doc_id uuid;
  ids jsonb := '{}'::jsonb;
  pending integer;
  total_pending integer := 0;
begin
  foreach k in array kinds loop
    -- The new version replaces the old ones: their open suggestions no longer apply.
    update public.suggestions s
      set decision = 'superseded', decided_at = now()
      from public.documents d
      where s.document_id = d.id and d.job_id = job and d.kind = k and s.decision = 'pending';

    select count(*) into pending
      from jsonb_array_elements(coalesce(payload -> 'suggestions', '[]'::jsonb)) s
      where s ->> 'document' = k;
    total_pending := total_pending + pending;

    insert into public.documents (job_id, kind, version, template, content, state, model, cost_usd)
    values (
      job,
      k,
      coalesce((select max(version) from public.documents where job_id = job and kind = k), 0) + 1,
      payload -> k ->> 'template',
      payload -> k -> 'content',
      case when pending > 0 then 'needs_approval' else 'pending_render' end,
      payload ->> 'model',
      (payload ->> 'cost_usd')::numeric / 2
    )
    returning id into doc_id;
    ids := ids || jsonb_build_object(k, doc_id);

    insert into public.suggestions (document_id, path, suggested_text, rationale)
    select doc_id, s ->> 'path', s ->> 'suggested_text', s ->> 'rationale'
      from jsonb_array_elements(coalesce(payload -> 'suggestions', '[]'::jsonb)) s
      where s ->> 'document' = k;
  end loop;

  update public.jobs
    set pipeline_state = case when total_pending > 0 then 'needs_approval' else 'tailoring' end::public.pipeline_state
    where id = job;

  return ids || jsonb_build_object('suggestions', total_pending);
end;
$$;
revoke execute on function public.save_tailored(uuid, jsonb) from public, anon, authenticated;
grant execute on function public.save_tailored(uuid, jsonb) to service_role;

-- Backfill: close open suggestions that belong to a replaced (not the newest) version.
update public.suggestions s
  set decision = 'superseded', decided_at = now()
  from public.documents d
  where s.document_id = d.id
    and s.decision = 'pending'
    and d.version < (select max(d2.version) from public.documents d2 where d2.job_id = d.job_id and d2.kind = d.kind);

update public.jobs set tags = array_remove(tags, 'immediate-start') where 'immediate-start' = any(tags);
