-- Milestone 4: tailored documents.

-- Documents wait for approval, then for rendering, then are final.
alter table public.documents drop constraint documents_state_check;
alter table public.documents add constraint documents_state_check
  check (state in ('needs_approval', 'pending_render', 'final', 'error'));

-- Kojo can edit a suggestion's text before approving it.
alter table public.suggestions add column final_text text;
grant update (final_text) on public.suggestions to authenticated;

-- New run kinds for the Mac's tailoring and on-demand task processing.
alter table public.runs drop constraint runs_kind_check;
alter table public.runs add constraint runs_kind_check
  check (kind in ('daily', 'local', 'scoring', 'tailoring', 'tasks', 'on_demand'));

-- The website reads task progress live.
grant update (step) on public.tasks to service_role;

-- ---------------------------------------------------------------------------
-- save_tailored: store a new version of both documents plus their suggestions
-- ---------------------------------------------------------------------------
-- payload: {resume: {template, content}, cover_letter: {template, content},
--           suggestions: [{document: 'resume'|'cover_letter', path, suggested_text, rationale}],
--           model, cost_usd}
create function public.save_tailored(job uuid, payload jsonb)
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
