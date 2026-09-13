-- ScientificBrain v0.9 collaborative research workspace and richer access provenance
alter table public.scibrain_folder_papers add column if not exists access_kind text not null default 'unknown';
alter table public.scibrain_folder_papers add column if not exists access_label text;
alter table public.scibrain_folder_papers add column if not exists system_can_read boolean not null default false;
alter table public.scibrain_folder_papers add column if not exists access_url text;
alter table public.scibrain_folder_papers add column if not exists access_license text;
alter table public.scibrain_folder_papers add column if not exists oa_status text;

update public.scibrain_folder_papers
set access_kind = case
  when storage_path is not null then 'uploaded'
  when access_status = 'open_access' then 'open_access'
  when access_status = 'manual_download' then 'closed_or_unknown'
  when access_status = 'unavailable' then 'unavailable'
  else coalesce(nullif(access_kind, ''), 'unknown')
end,
system_can_read = case
  when storage_path is not null then true
  when pdf_url is not null then true
  else system_can_read
end,
access_url = coalesce(access_url, pdf_url, source_url),
access_label = coalesce(access_label,
  case
    when storage_path is not null then 'PDF privado cargado'
    when access_status = 'open_access' then 'Open Access'
    when access_status = 'manual_download' then 'Acceso manual / OA no confirmado'
    when access_status = 'unavailable' then 'No disponible'
    else 'Metadatos disponibles'
  end
);

alter table public.scibrain_folder_papers drop constraint if exists scibrain_folder_papers_access_kind_check;
alter table public.scibrain_folder_papers add constraint scibrain_folder_papers_access_kind_check
check (access_kind in ('uploaded','open_access','public_repository','public_copy','public_pdf','public_page','closed_or_unknown','metadata_only','unavailable','unknown'));

create table if not exists public.scibrain_research_documents (
  document_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  project_id text references public.scibrain_projects(project_id) on delete set null,
  topic text not null default '',
  sections jsonb not null default '{}'::jsonb,
  evidence_manifest jsonb not null default '[]'::jsonb,
  generated_from_paper_ids text[] not null default '{}',
  revision integer not null default 1,
  status text not null default 'draft' check (status in ('draft','review','revised','final')),
  last_generated_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(owner_id, folder_id)
);

create index if not exists idx_scibrain_research_documents_owner_folder
on public.scibrain_research_documents(owner_id, folder_id, updated_at desc);

drop trigger if exists scibrain_research_documents_updated_at on public.scibrain_research_documents;
create trigger scibrain_research_documents_updated_at
before update on public.scibrain_research_documents
for each row execute function public.scibrain_set_updated_at();

create table if not exists public.scibrain_discussion_messages (
  message_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  document_id uuid references public.scibrain_research_documents(document_id) on delete cascade,
  message_role text not null check (message_role in ('user','agent','system')),
  agent_id text,
  section_key text,
  content text not null,
  evidence_refs jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_scibrain_discussion_messages_folder
on public.scibrain_discussion_messages(owner_id, folder_id, created_at asc);

alter table public.scibrain_research_documents enable row level security;
alter table public.scibrain_discussion_messages enable row level security;

drop policy if exists "scibrain_research_documents_owner" on public.scibrain_research_documents;
create policy "scibrain_research_documents_owner" on public.scibrain_research_documents
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_discussion_messages_owner" on public.scibrain_discussion_messages;
create policy "scibrain_discussion_messages_owner" on public.scibrain_discussion_messages
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

revoke all on public.scibrain_research_documents, public.scibrain_discussion_messages from anon;
grant select, insert, update, delete on public.scibrain_research_documents, public.scibrain_discussion_messages to authenticated;
