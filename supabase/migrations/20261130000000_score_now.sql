-- "Score now" on the Today page: the website asks the Mac to score the jobs waiting to be
-- scored right away, instead of at 7:30 the next morning. A score task isn't about one job,
-- so it has no job_id. The Mac reports progress in `result` while it works:
--   {"waiting": true}                                   another scoring run is going; queued behind it
--   {"total": 23, "scored": 12, "matches": 5, ...}      as each batch finishes, then the final counts
alter table public.tasks drop constraint tasks_kind_check;
alter table public.tasks add constraint tasks_kind_check
  check (kind in ('ingest', 'tailor', 'render', 'regenerate', 'score'));

alter table public.tasks drop constraint tasks_step_check;
alter table public.tasks add constraint tasks_step_check
  check (step in ('queued', 'writing', 'rendering', 'scoring', 'ready', 'error'));

alter table public.tasks add constraint tasks_score_has_no_job
  check (kind <> 'score' or job_id is null);

alter table public.tasks add column result jsonb;
comment on column public.tasks.result is
  'Progress and outcome reported by the Mac (score tasks: waiting, total, scored, matches, below, failed)';
