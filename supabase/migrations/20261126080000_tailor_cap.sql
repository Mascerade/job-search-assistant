-- Milestone 4: how many matches get tailored documents per day (best fit first).
update public.settings
  set data = data || '{"tailor_daily_cap": 20}'::jsonb
  where id = 1 and not (data ? 'tailor_daily_cap');
