-- Careers platforms used by Boston-area universities (milestone 2):
-- Harvard (SmartRecruiters), Tufts (Jibe/iCIMS), BU (SilkRoad), UMass Boston (PageUp), MIT (Peopleclick).
alter type public.job_source add value if not exists 'smartrecruiters';
alter type public.job_source add value if not exists 'jibe';
alter type public.job_source add value if not exists 'silkroad';
alter type public.job_source add value if not exists 'pageup';
alter type public.job_source add value if not exists 'peopleclick';
