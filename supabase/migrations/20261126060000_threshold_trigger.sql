-- When the fit threshold changes in Settings, re-sort already-scored jobs right away
-- (matches vs. below threshold) instead of waiting for them to be rescored.
create function public.apply_fit_threshold()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  if (new.data ->> 'fit_threshold') is distinct from (old.data ->> 'fit_threshold') then
    update public.jobs
      set pipeline_state = case
        when fit_score >= (new.data ->> 'fit_threshold')::integer then 'scored'::public.pipeline_state
        else 'below_threshold'::public.pipeline_state
      end
      where pipeline_state in ('scored', 'below_threshold') and fit_score is not null;
  end if;
  return new;
end;
$$;

create trigger settings_apply_fit_threshold
  after update of data on public.settings
  for each row execute function public.apply_fit_threshold();
