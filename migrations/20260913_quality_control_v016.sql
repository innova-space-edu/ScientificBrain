create table if not exists public.scibrain_benchmark_runs (
  run_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  document_id uuid references public.scibrain_research_documents(document_id) on delete cascade,
  revision integer not null default 0,
  benchmark_type text not null default 'scientific_entailment_v1',
  score double precision,
  metrics jsonb not null default '{}'::jsonb,
  findings jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.scibrain_benchmark_runs enable row level security;

drop policy if exists scibrain_benchmark_runs_owner_all on public.scibrain_benchmark_runs;
create policy scibrain_benchmark_runs_owner_all
  on public.scibrain_benchmark_runs
  for all
  to authenticated
  using (owner_id = auth.uid())
  with check (owner_id = auth.uid());

create index if not exists scibrain_benchmark_runs_owner_folder_created_idx
  on public.scibrain_benchmark_runs(owner_id, folder_id, created_at desc);

create index if not exists scibrain_benchmark_runs_document_revision_idx
  on public.scibrain_benchmark_runs(document_id, revision desc);
