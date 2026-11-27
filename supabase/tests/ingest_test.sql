-- Tests for the job-feed functions. Run with: npx supabase test db
begin;
select plan(18);

-- First ingest: one new posting
select is(
  public.ingest_postings('[{"source":"greenhouse","source_job_id":"acme:1","source_board":"greenhouse:acme",
    "company":"Acme","title":"Software Engineer","location":"Boston, MA","dedupe_key":"acme|software engineer|boston",
    "track":"software","pipeline_state":"new","tags":["remote-ok"]}]'::jsonb),
  '{"inserted": 1, "updated": 0, "duplicates": 0}'::jsonb,
  'new posting is inserted'
);

-- Kojo moves it along; the pipeline scores it
update public.jobs set status = 'applied', notes = 'Referred by Sam', pipeline_state = 'scored'
  where source_job_id = 'acme:1';

-- Second ingest of the same posting, now with a changed title and a filter verdict
select is(
  public.ingest_postings('[{"source":"greenhouse","source_job_id":"acme:1","source_board":"greenhouse:acme",
    "company":"Acme","title":"Software Engineer I","location":"Boston, MA","dedupe_key":"acme|software engineer i|boston",
    "track":"software","pipeline_state":"filtered_out","filter_reason":"test"}]'::jsonb),
  '{"inserted": 0, "updated": 1, "duplicates": 0}'::jsonb,
  'existing posting is updated, not duplicated'
);
select is((select title from public.jobs where source_job_id = 'acme:1'), 'Software Engineer I', 'posting fields refresh');
select is((select status::text from public.jobs where source_job_id = 'acme:1'), 'applied', 'application status is untouched');
select is((select notes from public.jobs where source_job_id = 'acme:1'), 'Referred by Sam', 'notes are untouched');
select is((select pipeline_state::text from public.jobs where source_job_id = 'acme:1'), 'scored', 'pipeline progress past filtering is kept');
select is((select tags from public.jobs where source_job_id = 'acme:1'), array['remote-ok'], 'tags are kept');

-- Same job from another board (same dedupe key) is skipped
select is(
  public.ingest_postings('[{"source":"lever","source_job_id":"acme2:9","source_board":"lever:acme2",
    "company":"Acme","title":"Software Engineer I","location":"Boston, MA","dedupe_key":"acme|software engineer i|boston",
    "pipeline_state":"new"}]'::jsonb),
  '{"inserted": 0, "updated": 0, "duplicates": 1}'::jsonb,
  'cross-source duplicate is skipped'
);

-- Same board, same title and city, different id: a separate opening, not a duplicate
select is(
  public.ingest_postings('[{"source":"greenhouse","source_job_id":"acme:3","source_board":"greenhouse:acme",
    "company":"Acme","title":"Software Engineer I","location":"Boston, MA","dedupe_key":"acme|software engineer i|boston",
    "pipeline_state":"new"}]'::jsonb),
  '{"inserted": 1, "updated": 0, "duplicates": 0}'::jsonb,
  'two openings with the same title on one board are both kept'
);

-- Closing: a second posting on the board, then a fetch that only sees acme:2
select public.ingest_postings('[{"source":"greenhouse","source_job_id":"acme:2","source_board":"greenhouse:acme",
  "company":"Acme","title":"Data Analyst","dedupe_key":"acme|data analyst|boston","pipeline_state":"new"}]'::jsonb);
select is(public.close_missing_postings('greenhouse:acme', array['acme:2']), 2, 'postings missing from the board are closed');
select isnt((select closed_at from public.jobs where source_job_id = 'acme:1'), null, 'missing posting gets closed_at');

-- Seeing it again reopens it
select public.ingest_postings('[{"source":"greenhouse","source_job_id":"acme:1","source_board":"greenhouse:acme",
  "company":"Acme","title":"Software Engineer I","dedupe_key":"acme|software engineer i|boston","pipeline_state":"new"}]'::jsonb);
select is((select closed_at from public.jobs where source_job_id = 'acme:1'), null, 'reappearing posting is reopened');

-- A job added by hand, later listed by a source at the same URL: linked, not duplicated
insert into public.jobs (company, title, url, status, notes)
  values ('Broad', 'Computational Associate I', 'https://example.avature.net/careers/JobDetail/CA-I/7/', 'applied', 'Applied 11/26');
select is(
  public.ingest_postings('[{"source":"avature","source_job_id":"example.avature.net:7","source_board":"avature:example.avature.net",
    "url":"https://example.avature.net/careers/JobDetail/CA-I/7","company":"Broad Institute",
    "title":"Early Career Researchers - Computational Associate I","dedupe_key":"broad institute|early career researchers|cambridge",
    "track":"research","pipeline_state":"new"}]'::jsonb),
  '{"inserted": 0, "updated": 1, "duplicates": 0}'::jsonb,
  'a posting you added by hand is linked by URL, not added again'
);
select is(
  (select array[source::text, title, status::text, notes, source_board] from public.jobs where url like '%/CA-I/7/'),
  array['manual', 'Computational Associate I', 'applied', 'Applied 11/26', 'avature:example.avature.net'],
  'your entry keeps its title, status, and notes and is tied to the board'
);
select is(
  public.ingest_postings('[{"source":"avature","source_job_id":"example.avature.net:7","source_board":"avature:example.avature.net",
    "url":"https://example.avature.net/careers/JobDetail/CA-I/7","company":"Broad Institute",
    "title":"Early Career Researchers - Computational Associate I","pipeline_state":"new"}]'::jsonb),
  '{"inserted": 0, "updated": 1, "duplicates": 0}'::jsonb,
  'the next run finds the linked entry again'
);
select is(public.close_missing_postings('avature:example.avature.net', array[]::text[]), 1, 'a linked entry closes when the posting is taken down');
select is((select count(*)::integer from public.jobs where url ilike '%/CA-I/7%'), 1, 'still one row for that posting');

-- The website's roles can't call the pipeline functions
set local role authenticated;
select throws_ok($$ select public.ingest_postings('[]'::jsonb) $$, '42501', null, 'signed-in users cannot ingest');

select * from finish();
rollback;
