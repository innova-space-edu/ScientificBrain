create table if not exists public.scibrain_discovery_runs (
  run_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  document_id uuid null references public.scibrain_research_documents(document_id) on delete set null,
  focus text,
  from_year integer not null default 1900 check (from_year between 1900 and 2100),
  status text not null default 'running' check (status in ('running','completed','partial','failed')),
  plan jsonb not null default '{}'::jsonb,
  queries jsonb not null default '[]'::jsonb,
  criteria jsonb not null default '{}'::jsonb,
  source_summary jsonb not null default '{}'::jsonb,
  candidate_count integer not null default 0 check (candidate_count >= 0),
  errors jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.scibrain_screening_candidates (
  candidate_id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.scibrain_discovery_runs(run_id) on delete cascade,
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  canonical_key text not null,
  canonical_id text,
  title text not null,
  authors jsonb not null default '[]'::jsonb,
  publication_date text,
  journal text,
  doi text,
  arxiv_id text,
  source text not null default 'web',
  source_url text,
  pdf_url text,
  abstract text not null default '',
  access_status text not null default 'metadata_only',
  access_kind text not null default 'unknown',
  access_label text not null default 'Acceso no verificado',
  system_can_read boolean not null default false,
  cited_by_count integer not null default 0 check (cited_by_count >= 0),
  query_origins jsonb not null default '[]'::jsonb,
  target_gaps jsonb not null default '[]'::jsonb,
  target_hypotheses jsonb not null default '[]'::jsonb,
  preliminary_score double precision not null default 0 check (preliminary_score between 0 and 1),
  relevance_score double precision not null default 0 check (relevance_score between 0 and 1),
  screening_reason text not null default '',
  expected_contribution text not null default '',
  risks jsonb not null default '[]'::jsonb,
  recommendation text not null default 'review' check (recommendation in ('include','review','exclude')),
  decision text not null default 'pending' check (decision in ('pending','included','excluded','later')),
  decision_reason text,
  added_item_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(owner_id, folder_id, canonical_key)
);

create index if not exists scibrain_discovery_runs_owner_folder_idx
  on public.scibrain_discovery_runs(owner_id, folder_id, created_at desc);
create index if not exists scibrain_screening_candidates_owner_folder_idx
  on public.scibrain_screening_candidates(owner_id, folder_id, relevance_score desc, updated_at desc);
create index if not exists scibrain_screening_candidates_decision_idx
  on public.scibrain_screening_candidates(owner_id, folder_id, decision, relevance_score desc);
create index if not exists scibrain_screening_candidates_run_idx
  on public.scibrain_screening_candidates(run_id, relevance_score desc);

alter table public.scibrain_discovery_runs enable row level security;
alter table public.scibrain_screening_candidates enable row level security;

drop policy if exists scibrain_discovery_runs_owner_all on public.scibrain_discovery_runs;
create policy scibrain_discovery_runs_owner_all on public.scibrain_discovery_runs
  for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

drop policy if exists scibrain_screening_candidates_owner_all on public.scibrain_screening_candidates;
create policy scibrain_screening_candidates_owner_all on public.scibrain_screening_candidates
  for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

grant select, insert, update, delete on public.scibrain_discovery_runs to authenticated;
grant select, insert, update, delete on public.scibrain_screening_candidates to authenticated;

create or replace function public.scibrain_v21_touch_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists scibrain_discovery_runs_touch_updated_at on public.scibrain_discovery_runs;
create trigger scibrain_discovery_runs_touch_updated_at
before update on public.scibrain_discovery_runs
for each row execute function public.scibrain_v21_touch_updated_at();

drop trigger if exists scibrain_screening_candidates_touch_updated_at on public.scibrain_screening_candidates;
create trigger scibrain_screening_candidates_touch_updated_at
before update on public.scibrain_screening_candidates
for each row execute function public.scibrain_v21_touch_updated_at();
