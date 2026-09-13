alter table public.scibrain_paper_memory
  add column if not exists structure jsonb not null default '{}'::jsonb,
  add column if not exists asset_summary jsonb not null default '{}'::jsonb,
  add column if not exists indexed_at timestamptz;

alter table public.scibrain_research_documents
  add column if not exists corpus_fingerprint text,
  add column if not exists stale_reason text,
  add column if not exists last_evidence_refresh_at timestamptz;

create table if not exists public.scibrain_paper_chunks (
  chunk_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  paper_id text not null,
  chunk_index integer not null,
  page_start integer not null,
  page_end integer not null,
  section_label text,
  kind text not null default 'text',
  text text not null,
  content_hash text not null,
  token_estimate integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  search_vector tsvector generated always as (to_tsvector('simple', coalesce(text,''))) stored,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(folder_id, paper_id, chunk_index)
);
create index if not exists scibrain_paper_chunks_owner_folder_idx on public.scibrain_paper_chunks(owner_id, folder_id, paper_id);
create index if not exists scibrain_paper_chunks_search_idx on public.scibrain_paper_chunks using gin(search_vector);
alter table public.scibrain_paper_chunks enable row level security;
drop policy if exists scibrain_paper_chunks_owner_all on public.scibrain_paper_chunks;
create policy scibrain_paper_chunks_owner_all on public.scibrain_paper_chunks
for all using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

create table if not exists public.scibrain_paper_assets (
  asset_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  paper_id text not null,
  page integer not null,
  asset_type text not null,
  label text,
  caption text,
  text text,
  content_hash text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(folder_id, paper_id, page, asset_type, content_hash)
);
create index if not exists scibrain_paper_assets_owner_folder_idx on public.scibrain_paper_assets(owner_id, folder_id, paper_id, asset_type);
alter table public.scibrain_paper_assets enable row level security;
drop policy if exists scibrain_paper_assets_owner_all on public.scibrain_paper_assets;
create policy scibrain_paper_assets_owner_all on public.scibrain_paper_assets
for all using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

create table if not exists public.scibrain_research_versions (
  version_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  document_id uuid not null references public.scibrain_research_documents(document_id) on delete cascade,
  revision integer not null,
  reason text not null default 'update',
  topic text not null default '',
  research_brief jsonb not null default '{}'::jsonb,
  sections jsonb not null default '{}'::jsonb,
  evidence_manifest jsonb not null default '{}'::jsonb,
  novelty_assessment jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(document_id, revision)
);
create index if not exists scibrain_research_versions_owner_doc_idx on public.scibrain_research_versions(owner_id, document_id, revision desc);
alter table public.scibrain_research_versions enable row level security;
drop policy if exists scibrain_research_versions_owner_all on public.scibrain_research_versions;
create policy scibrain_research_versions_owner_all on public.scibrain_research_versions
for all using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

create table if not exists public.scibrain_usage_events (
  event_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  folder_id uuid references public.scibrain_folders(folder_id) on delete cascade,
  event_type text not null,
  paper_id text,
  document_id uuid,
  duration_ms integer,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists scibrain_usage_events_owner_time_idx on public.scibrain_usage_events(owner_id, created_at desc);
alter table public.scibrain_usage_events enable row level security;
drop policy if exists scibrain_usage_events_owner_all on public.scibrain_usage_events;
create policy scibrain_usage_events_owner_all on public.scibrain_usage_events
for all using (owner_id = (select auth.uid())) with check (owner_id = (select auth.uid()));

create or replace function public.scibrain_search_paper_chunks(
  p_folder_id uuid,
  p_paper_id text,
  p_query text,
  p_limit integer default 12
)
returns table(
  chunk_id uuid,
  chunk_index integer,
  page_start integer,
  page_end integer,
  section_label text,
  kind text,
  text text,
  rank real
)
language sql
stable
security invoker
set search_path = public
as $$
  select c.chunk_id, c.chunk_index, c.page_start, c.page_end, c.section_label, c.kind, c.text,
         ts_rank_cd(c.search_vector, websearch_to_tsquery('simple', coalesce(p_query,'')))::real as rank
  from public.scibrain_paper_chunks c
  where c.owner_id = (select auth.uid())
    and c.folder_id = p_folder_id
    and c.paper_id = p_paper_id
    and (trim(coalesce(p_query,'')) = '' or c.search_vector @@ websearch_to_tsquery('simple', p_query))
  order by rank desc, c.chunk_index asc
  limit greatest(1, least(coalesce(p_limit,12), 30));
$$;
grant execute on function public.scibrain_search_paper_chunks(uuid,text,text,integer) to authenticated;
