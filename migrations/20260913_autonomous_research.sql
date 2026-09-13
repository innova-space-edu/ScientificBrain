-- ScientificBrain v0.11: persistent paper memory and guided deep-research state.
create table if not exists public.scibrain_paper_memory (
  memory_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  paper_id text not null,
  source_url text,
  content_hash text not null,
  page_count integer not null default 0,
  word_count integer not null default 0,
  char_count integer not null default 0,
  full_text text not null default '',
  pages jsonb not null default '[]'::jsonb,
  extraction_version text not null default 'pypdf-v1',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(owner_id, folder_id, paper_id)
);

alter table public.scibrain_paper_memory enable row level security;
drop policy if exists scibrain_paper_memory_owner_all on public.scibrain_paper_memory;
create policy scibrain_paper_memory_owner_all on public.scibrain_paper_memory
  for all to authenticated
  using (owner_id = (select auth.uid()))
  with check (owner_id = (select auth.uid()));
create index if not exists scibrain_paper_memory_folder_idx on public.scibrain_paper_memory(folder_id);
create index if not exists scibrain_paper_memory_paper_idx on public.scibrain_paper_memory(paper_id);
create index if not exists scibrain_paper_memory_search_idx on public.scibrain_paper_memory using gin (to_tsvector('simple', full_text));

alter table public.scibrain_research_documents
  add column if not exists research_brief jsonb not null default '{}'::jsonb,
  add column if not exists novelty_assessment jsonb not null default '{}'::jsonb,
  add column if not exists external_search_snapshot jsonb not null default '{}'::jsonb,
  add column if not exists research_mode text not null default 'guided_deep';
