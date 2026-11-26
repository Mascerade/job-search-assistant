-- The fit threshold chosen from the labeled evaluation set is 50 (at 70 only half of the
-- jobs Kojo wanted were shown). Make it the default for fresh databases; an existing
-- non-default choice is left alone.
update public.settings
  set data = jsonb_set(data, '{fit_threshold}', '50')
  where id = 1 and (data ->> 'fit_threshold')::integer = 70;
