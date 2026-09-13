alter table public.scibrain_folder_papers
  alter column canonical_id set default ('userdoc:' || gen_random_uuid()::text);

update public.scibrain_folder_papers
set canonical_id = 'userdoc:' || gen_random_uuid()::text
where canonical_id is null;

alter table public.scibrain_folder_papers
  alter column canonical_id set not null;
