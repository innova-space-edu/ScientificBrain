-- ScientificBrain multi-user workspaces
-- Target Supabase: https://cwbnvukerekgcedcyydd.supabase.co
-- Safe to re-run: objects are created or altered idempotently where possible.

create extension if not exists pgcrypto;

create or replace function public.scibrain_set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.scibrain_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  institution text,
  primary_area text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.scibrain_folders (
  folder_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  parent_id uuid references public.scibrain_folders(folder_id) on delete cascade,
  name text not null check (length(trim(name)) > 0),
  year integer check (year is null or year between 1900 and 2200),
  research_line text,
  area text,
  description text,
  paper_target integer not null default 100 check (paper_target between 1 and 5000),
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_scibrain_folders_owner on public.scibrain_folders(owner_id, parent_id, sort_order, name);
create index if not exists idx_scibrain_folders_classification on public.scibrain_folders(owner_id, year, research_line, area);

drop trigger if exists scibrain_folders_updated_at on public.scibrain_folders;
create trigger scibrain_folders_updated_at
before update on public.scibrain_folders
for each row execute function public.scibrain_set_updated_at();

-- Existing project/session tables are upgraded to user and folder scope.
alter table public.scibrain_projects add column if not exists owner_id uuid references auth.users(id) on delete cascade;
alter table public.scibrain_projects add column if not exists folder_id uuid references public.scibrain_folders(folder_id) on delete set null;
alter table public.scibrain_states add column if not exists owner_id uuid references auth.users(id) on delete cascade;
alter table public.scibrain_states add column if not exists folder_id uuid references public.scibrain_folders(folder_id) on delete set null;
alter table public.scibrain_artifacts add column if not exists owner_id uuid references auth.users(id) on delete cascade;
alter table public.scibrain_jobs add column if not exists owner_id uuid references auth.users(id) on delete cascade;

create index if not exists idx_scibrain_projects_owner_folder on public.scibrain_projects(owner_id, folder_id, updated_at desc);
create index if not exists idx_scibrain_states_owner_folder on public.scibrain_states(owner_id, folder_id, updated_at desc);
create index if not exists idx_scibrain_artifacts_owner_session on public.scibrain_artifacts(owner_id, session_id, created_at);
create index if not exists idx_scibrain_jobs_owner_session on public.scibrain_jobs(owner_id, session_id, created_at desc);

-- User-scoped paper library. The same DOI can exist independently in different users/folders.
create table if not exists public.scibrain_folder_papers (
  item_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  project_id text references public.scibrain_projects(project_id) on delete set null,
  canonical_id text,
  title text not null,
  authors jsonb not null default '[]'::jsonb,
  publication_date date,
  journal text,
  doi text,
  arxiv_id text,
  source_type text not null default 'upload' check (source_type in ('upload','openalex','arxiv','crossref','web','manual')),
  source_url text,
  pdf_url text,
  access_status text not null default 'uploaded' check (access_status in ('uploaded','open_access','metadata_only','manual_download','unavailable','error')),
  manual_lookup_required boolean not null default false,
  storage_path text,
  original_filename text,
  mime_type text,
  file_size_bytes bigint,
  review_depth text not null default 'metadata_verified',
  record jsonb not null default '{}'::jsonb,
  analysis jsonb,
  critique jsonb,
  specialist_reviews jsonb not null default '[]'::jsonb,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists uq_scibrain_folder_papers_canonical
  on public.scibrain_folder_papers(owner_id, folder_id, canonical_id)
  where canonical_id is not null;
create index if not exists idx_scibrain_folder_papers_folder on public.scibrain_folder_papers(owner_id, folder_id, created_at desc);
create index if not exists idx_scibrain_folder_papers_doi on public.scibrain_folder_papers(lower(doi)) where doi is not null;

drop trigger if exists scibrain_folder_papers_updated_at on public.scibrain_folder_papers;
create trigger scibrain_folder_papers_updated_at
before update on public.scibrain_folder_papers
for each row execute function public.scibrain_set_updated_at();

create table if not exists public.scibrain_research_searches (
  search_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  project_id text references public.scibrain_projects(project_id) on delete set null,
  query text not null,
  sources text[] not null default '{}',
  result_count integer not null default 0,
  results jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_scibrain_research_searches_folder on public.scibrain_research_searches(owner_id, folder_id, created_at desc);

-- Profiles are created automatically for new Supabase Auth users.
create or replace function public.scibrain_handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.scibrain_profiles(user_id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1)))
  on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_scibrain_auth_user_created on auth.users;
create trigger on_scibrain_auth_user_created
after insert on auth.users
for each row execute function public.scibrain_handle_new_user();

-- RLS: every signed-in user sees only their own research workspace.
alter table public.scibrain_profiles enable row level security;
alter table public.scibrain_folders enable row level security;
alter table public.scibrain_projects enable row level security;
alter table public.scibrain_states enable row level security;
alter table public.scibrain_artifacts enable row level security;
alter table public.scibrain_jobs enable row level security;
alter table public.scibrain_folder_papers enable row level security;
alter table public.scibrain_research_searches enable row level security;

-- Replace policies by stable names.
drop policy if exists "scibrain_profiles_owner" on public.scibrain_profiles;
create policy "scibrain_profiles_owner" on public.scibrain_profiles
for all to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "scibrain_folders_owner" on public.scibrain_folders;
create policy "scibrain_folders_owner" on public.scibrain_folders
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_projects_owner" on public.scibrain_projects;
create policy "scibrain_projects_owner" on public.scibrain_projects
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_states_owner" on public.scibrain_states;
create policy "scibrain_states_owner" on public.scibrain_states
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_artifacts_owner" on public.scibrain_artifacts;
create policy "scibrain_artifacts_owner" on public.scibrain_artifacts
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_jobs_owner" on public.scibrain_jobs;
create policy "scibrain_jobs_owner" on public.scibrain_jobs
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_folder_papers_owner" on public.scibrain_folder_papers;
create policy "scibrain_folder_papers_owner" on public.scibrain_folder_papers
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_research_searches_owner" on public.scibrain_research_searches;
create policy "scibrain_research_searches_owner" on public.scibrain_research_searches
for all to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

revoke all on public.scibrain_profiles, public.scibrain_folders, public.scibrain_folder_papers, public.scibrain_research_searches from anon;
grant select, insert, update, delete on public.scibrain_profiles, public.scibrain_folders, public.scibrain_folder_papers, public.scibrain_research_searches to authenticated;
grant select, insert, update, delete on public.scibrain_projects, public.scibrain_states, public.scibrain_artifacts, public.scibrain_jobs to authenticated;

-- Private Storage bucket. Object path convention:
--   <auth.uid()>/<folder_id>/<document_uuid>-<filename>
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('scibrain-papers', 'scibrain-papers', false, 104857600, array['application/pdf'])
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "scibrain_storage_select_own" on storage.objects;
create policy "scibrain_storage_select_own" on storage.objects
for select to authenticated
using (bucket_id = 'scibrain-papers' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "scibrain_storage_insert_own" on storage.objects;
create policy "scibrain_storage_insert_own" on storage.objects
for insert to authenticated
with check (bucket_id = 'scibrain-papers' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "scibrain_storage_update_own" on storage.objects;
create policy "scibrain_storage_update_own" on storage.objects
for update to authenticated
using (bucket_id = 'scibrain-papers' and (storage.foldername(name))[1] = (select auth.uid())::text)
with check (bucket_id = 'scibrain-papers' and (storage.foldername(name))[1] = (select auth.uid())::text);

drop policy if exists "scibrain_storage_delete_own" on storage.objects;
create policy "scibrain_storage_delete_own" on storage.objects
for delete to authenticated
using (bucket_id = 'scibrain-papers' and (storage.foldername(name))[1] = (select auth.uid())::text);
