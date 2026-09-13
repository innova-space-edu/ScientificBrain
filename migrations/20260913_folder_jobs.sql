alter table public.scibrain_jobs
  add column if not exists folder_id uuid references public.scibrain_folders(folder_id) on delete cascade;

update public.scibrain_jobs j
set folder_id = s.folder_id
from public.scibrain_states s
where j.folder_id is null
  and j.session_id = s.session_id;

create index if not exists idx_scibrain_jobs_owner_folder
  on public.scibrain_jobs(owner_id, folder_id, status, created_at);
