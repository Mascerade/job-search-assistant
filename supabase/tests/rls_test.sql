-- Security + trigger tests for the initial schema. Run with: npx supabase test db
begin;
select plan(17);

-- Two throwaway users: one registered as owner, one not.
insert into auth.users (id, email, aud, role)
values
  ('11111111-1111-1111-1111-111111111111', 'owner-test@example.com', 'authenticated', 'authenticated'),
  ('22222222-2222-2222-2222-222222222222', 'stranger@example.com', 'authenticated', 'authenticated');
insert into public.app_owner (user_id) values ('11111111-1111-1111-1111-111111111111');

-- A document + suggestion created by the "pipeline" (superuser here).
insert into public.jobs (id, company, title)
  values ('aaaaaaaa-0000-0000-0000-000000000001', 'Pipeline Co', 'Seeded Job');
insert into public.documents (id, job_id, kind, template, content)
  values ('bbbbbbbb-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000001', 'resume', 'technical', '{}');
insert into public.suggestions (id, document_id, path, suggested_text, rationale)
  values ('cccccccc-0000-0000-0000-000000000001', 'bbbbbbbb-0000-0000-0000-000000000001', 'experience.0.bullets.0', 'New bullet', 'Because');

-- ===== As the owner =====
set local role authenticated;
set local request.jwt.claims = '{"sub": "11111111-1111-1111-1111-111111111111", "role": "authenticated"}';

select ok(public.is_owner(), 'owner is recognized');

select lives_ok(
  $$ insert into public.jobs (id, company, title) values ('aaaaaaaa-0000-0000-0000-000000000002', 'Harvard', 'Program Coordinator') $$,
  'owner can add a job'
);

select is(
  (select count(*)::int from public.status_history where job_id = 'aaaaaaaa-0000-0000-0000-000000000002'),
  1, 'adding a job records its first status'
);

select lives_ok(
  $$ update public.jobs set status = 'applied' where id = 'aaaaaaaa-0000-0000-0000-000000000002' $$,
  'owner can change status'
);

select is(
  (select count(*)::int from public.status_history where job_id = 'aaaaaaaa-0000-0000-0000-000000000002'),
  2, 'status change is recorded in history'
);

select isnt(
  (select applied_at from public.jobs where id = 'aaaaaaaa-0000-0000-0000-000000000002'),
  null, 'moving to applied stamps applied_at'
);

select is(
  (select count(*)::int from public.jobs where id in ('aaaaaaaa-0000-0000-0000-000000000001', 'aaaaaaaa-0000-0000-0000-000000000002')),
  2, 'owner sees every job'
);

select throws_ok(
  $$ insert into public.status_history (job_id, to_status) values ('aaaaaaaa-0000-0000-0000-000000000002', 'offer') $$,
  '42501', null, 'owner cannot write history directly'
);

select lives_ok(
  $$ update public.suggestions set decision = 'approved', decided_at = now() where id = 'cccccccc-0000-0000-0000-000000000001' $$,
  'owner can approve a suggestion'
);

select throws_ok(
  $$ update public.suggestions set suggested_text = 'tampered' where id = 'cccccccc-0000-0000-0000-000000000001' $$,
  '42501', null, 'owner cannot rewrite suggestion text'
);

select lives_ok(
  $$ insert into public.tasks (job_id, kind) values ('aaaaaaaa-0000-0000-0000-000000000002', 'render') $$,
  'owner can request a task'
);

select is(
  (select (data ->> 'fit_threshold')::int from public.settings where id = 1),
  70, 'owner can read default settings'
);

-- ===== As a different signed-in user =====
set local request.jwt.claims = '{"sub": "22222222-2222-2222-2222-222222222222", "role": "authenticated"}';

select ok(not public.is_owner(), 'stranger is not the owner');
select is((select count(*)::int from public.jobs), 0, 'stranger sees no jobs');
select throws_ok(
  $$ insert into public.jobs (company, title) values ('Evil', 'Spam') $$,
  '42501', null, 'stranger cannot add jobs'
);
select is((select count(*)::int from public.profile_versions), 0, 'stranger sees no profile');

-- ===== Anonymous =====
reset role;
set local role anon;
set local request.jwt.claims = '{"role": "anon"}';
select is((select count(*)::int from public.jobs), 0, 'anonymous visitors see no jobs');

select * from finish();
rollback;
