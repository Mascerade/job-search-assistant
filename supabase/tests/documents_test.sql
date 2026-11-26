-- Tests for save_tailored and suggestion permissions. Run with: npx supabase test db
begin;
select plan(8);

insert into auth.users (id, email, aud, role)
  values ('33333333-3333-3333-3333-333333333333', 'owner-doc@example.com', 'authenticated', 'authenticated');
insert into public.app_owner (user_id) values ('33333333-3333-3333-3333-333333333333');
insert into public.jobs (id, company, title, pipeline_state) values
  ('eeeeeeee-0000-0000-0000-000000000001', 'Acme', 'Program Coordinator', 'scored');

select is(
  public.save_tailored('eeeeeeee-0000-0000-0000-000000000001', '{
    "resume": {"template": "admin", "content": {"tailored": {}}},
    "cover_letter": {"template": "admin", "content": {"tailored": {}}},
    "suggestions": [{"document": "cover_letter", "path": "cover.paragraphs.1", "suggested_text": "x", "rationale": "y"}],
    "model": "claude-opus-5-5", "cost_usd": 0.2}'::jsonb) ->> 'suggestions',
  '1', 'one suggestion saved'
);
select is((select state from public.documents where job_id = 'eeeeeeee-0000-0000-0000-000000000001' and kind = 'cover_letter'),
  'needs_approval', 'document with a suggestion waits for approval');
select is((select state from public.documents where job_id = 'eeeeeeee-0000-0000-0000-000000000001' and kind = 'resume'),
  'pending_render', 'document without suggestions goes straight to rendering');
select is((select pipeline_state::text from public.jobs where id = 'eeeeeeee-0000-0000-0000-000000000001'),
  'needs_approval', 'job waits for approval');

select public.save_tailored('eeeeeeee-0000-0000-0000-000000000001',
  '{"resume": {"template": "admin", "content": {}}, "cover_letter": {"template": "admin", "content": {}}, "suggestions": []}'::jsonb);
select is((select max(version) from public.documents where job_id = 'eeeeeeee-0000-0000-0000-000000000001' and kind = 'resume'),
  2, 'regenerating creates version 2');

-- The owner can approve and edit a suggestion, but not change what was suggested.
set local role authenticated;
set local request.jwt.claims = '{"sub": "33333333-3333-3333-3333-333333333333", "role": "authenticated"}';
select lives_ok($$ update public.suggestions set decision = 'approved', final_text = 'edited', decided_at = now()
  where path = 'cover.paragraphs.1' $$, 'owner can approve with an edit');
select throws_ok($$ update public.suggestions set rationale = 'tampered' where path = 'cover.paragraphs.1' $$,
  '42501', null, 'owner cannot rewrite the rationale');
select throws_ok($$ select public.save_tailored('eeeeeeee-0000-0000-0000-000000000001', '{}'::jsonb) $$,
  '42501', null, 'signed-in users cannot save documents directly');

select * from finish();
rollback;
