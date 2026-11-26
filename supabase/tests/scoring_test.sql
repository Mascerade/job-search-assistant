-- Tests for record_scores. Run with: npx supabase test db
begin;
select plan(16);

insert into public.jobs (id, company, title, pipeline_state, tags) values
  ('dddddddd-0000-0000-0000-000000000001', 'Acme', 'Program Coordinator', 'new', array['location-unclear']),
  ('dddddddd-0000-0000-0000-000000000002', 'Acme', 'Data Analyst', 'new', '{}'),
  ('dddddddd-0000-0000-0000-000000000003', 'Acme', 'Software Engineer', 'tailoring', '{}');

select is(
  public.record_scores('[
    {"job_id":"dddddddd-0000-0000-0000-000000000001","score":88,"reason":"Strong admin match","track":"program_admin",
     "keep":true,"tags":["immediate-start"],"model":"claude-haiku-5-5","input_tokens":1000,"output_tokens":100,"cost_usd":0.001},
    {"job_id":"dddddddd-0000-0000-0000-000000000002","score":41,"reason":"Needs SQL depth","track":"software",
     "keep":false,"model":"claude-haiku-5-5"},
    {"job_id":"dddddddd-0000-0000-0000-000000000003","score":90,"reason":"Rescored","keep":true,"model":"claude-haiku-5-5"}
  ]'::jsonb),
  3, 'three scores saved'
);

select is((select pipeline_state::text from public.jobs where id = 'dddddddd-0000-0000-0000-000000000001'), 'scored', 'above threshold → scored');
select is((select fit_score::int from public.jobs where id = 'dddddddd-0000-0000-0000-000000000001'), 88, 'fit_score copied onto the job');
select is((select tags from public.jobs where id = 'dddddddd-0000-0000-0000-000000000001'),
  array['immediate-start', 'location-unclear'], 'tags are merged, not replaced');
select is((select pipeline_state::text from public.jobs where id = 'dddddddd-0000-0000-0000-000000000002'), 'below_threshold', 'below threshold → hidden');
select is((select track::text from public.jobs where id = 'dddddddd-0000-0000-0000-000000000002'), 'software', 'the AI can correct the track');
select is((select pipeline_state::text from public.jobs where id = 'dddddddd-0000-0000-0000-000000000003'), 'tailoring', 'later pipeline progress is kept');
select is((select count(*)::int from public.scores where job_id = 'dddddddd-0000-0000-0000-000000000001'), 1, 'score history row written');

-- Lowering the threshold in Settings moves the 41 into matches; raising it moves the 88 out
update public.settings set data = jsonb_set(data, '{fit_threshold}', '40') where id = 1;
select is((select pipeline_state::text from public.jobs where id = 'dddddddd-0000-0000-0000-000000000002'), 'scored', 'lower threshold → becomes a match');
update public.settings set data = jsonb_set(data, '{fit_threshold}', '90') where id = 1;
select is((select pipeline_state::text from public.jobs where id = 'dddddddd-0000-0000-0000-000000000001'), 'below_threshold', 'higher threshold → hidden');

-- Start windows (timing.py): copied from a score that carries one, or saved by record_timing
select is(
  public.record_scores('[
    {"job_id":"dddddddd-0000-0000-0000-000000000002","score":45,"reason":"Rescored","keep":false,"model":"m",
     "start":{"kind":"date","earliest":"2027-06-01","latest":"2027-08-31","term_end":null,"note":"Summer 2027 cohort"}}
  ]'::jsonb),
  1, 'a score with a start window is saved'
);
select is(
  (select row(start_kind, start_from, start_to, term_end, start_note)::text from public.jobs
    where id = 'dddddddd-0000-0000-0000-000000000002'),
  row('date', '2027-06-01'::date, '2027-08-31'::date, null::date, 'Summer 2027 cohort')::text,
  'the start window is copied onto the job'
);
select is(
  public.record_timing('[
    {"job_id":"dddddddd-0000-0000-0000-000000000003",
     "start":{"kind":"unstated","earliest":null,"latest":null,"term_end":"2027-06-30","note":""}}
  ]'::jsonb),
  1, 'record_timing saves a start window'
);
select is(
  (select row(start_kind, start_from, term_end, start_note)::text from public.jobs
    where id = 'dddddddd-0000-0000-0000-000000000003'),
  row('unstated', null::date, '2027-06-30'::date, null::text)::text,
  'a term end date is kept even when the start is unstated; an empty note is stored as null'
);

set local role authenticated;
select throws_ok($$ select public.record_scores('[]'::jsonb) $$, '42501', null, 'signed-in users cannot write scores');
select throws_ok($$ select public.record_timing('[]'::jsonb) $$, '42501', null, 'signed-in users cannot write start dates');

select * from finish();
rollback;
