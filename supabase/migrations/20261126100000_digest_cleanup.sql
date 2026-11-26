-- Milestone 5: morning digest and cleanup runs.
alter table public.runs drop constraint runs_kind_check;
alter table public.runs add constraint runs_kind_check
  check (kind in ('daily', 'local', 'scoring', 'tailoring', 'tasks', 'digest', 'cleanup', 'on_demand'));
