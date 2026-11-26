-- Explicit table privileges for the API roles.
--
-- Newer hosted Supabase projects don't grant API roles access to tables created by
-- migrations (the local stack still does), so spell them out. Row-level security
-- still decides *which rows* each role sees; these grants only decide which
-- operations are possible at all. anon (signed-out visitors) gets nothing.

grant usage on schema public to authenticated, service_role;

-- Pipeline (secret key): full access; it bypasses RLS by design.
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;
alter default privileges in schema public grant select, insert, update, delete on tables to service_role;
alter default privileges in schema public grant usage, select on sequences to service_role;

-- Website (signed-in owner): only what the RLS policies allow anyway.
grant select on public.app_owner to authenticated;
grant select, insert, update, delete on public.jobs to authenticated;
grant select, insert on public.profile_versions to authenticated;
grant select on public.status_history, public.scores, public.documents, public.runs to authenticated;
grant select, update on public.settings to authenticated;
grant select, insert on public.tasks to authenticated;
grant select on public.suggestions to authenticated;
grant update (decision, decided_at) on public.suggestions to authenticated;
grant usage, select on all sequences in schema public to authenticated;

-- Used inside the RLS policies.
grant execute on function public.is_owner() to authenticated, service_role;
