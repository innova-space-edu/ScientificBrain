create table if not exists public.scibrain_studies (
  study_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  topic text not null,
  title text not null default '',
  research_question text not null default '',
  language text not null default 'es',
  sections jsonb not null default '{}'::jsonb,
  source_snapshot jsonb not null default '{}'::jsonb,
  status text not null default 'draft',
  revision integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.scibrain_study_reviews (
  review_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  study_id uuid not null references public.scibrain_studies(study_id) on delete cascade,
  section_key text not null,
  agent_role text not null,
  review jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.scibrain_discussion_messages (
  message_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  study_id uuid not null references public.scibrain_studies(study_id) on delete cascade,
  speaker text not null check (speaker in ('user','agent')),
  agent_role text,
  content text not null,
  source_refs jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_scibrain_studies_owner_folder_updated
  on public.scibrain_studies(owner_id, folder_id, updated_at desc);
create index if not exists idx_scibrain_study_reviews_study
  on public.scibrain_study_reviews(owner_id, study_id, created_at desc);
create index if not exists idx_scibrain_discussion_messages_study
  on public.scibrain_discussion_messages(owner_id, study_id, created_at asc);

alter table public.scibrain_studies enable row level security;
alter table public.scibrain_study_reviews enable row level security;
alter table public.scibrain_discussion_messages enable row level security;

drop policy if exists "scibrain_studies_select_own" on public.scibrain_studies;
create policy "scibrain_studies_select_own"
  on public.scibrain_studies for select to authenticated
  using (auth.uid() = owner_id);

drop policy if exists "scibrain_studies_insert_own" on public.scibrain_studies;
create policy "scibrain_studies_insert_own"
  on public.scibrain_studies for insert to authenticated
  with check (auth.uid() = owner_id);

drop policy if exists "scibrain_studies_update_own" on public.scibrain_studies;
create policy "scibrain_studies_update_own"
  on public.scibrain_studies for update to authenticated
  using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);

drop policy if exists "scibrain_studies_delete_own" on public.scibrain_studies;
create policy "scibrain_studies_delete_own"
  on public.scibrain_studies for delete to authenticated
  using (auth.uid() = owner_id);

drop policy if exists "scibrain_study_reviews_select_own" on public.scibrain_study_reviews;
create policy "scibrain_study_reviews_select_own"
  on public.scibrain_study_reviews for select to authenticated
  using (auth.uid() = owner_id);

drop policy if exists "scibrain_study_reviews_insert_own" on public.scibrain_study_reviews;
create policy "scibrain_study_reviews_insert_own"
  on public.scibrain_study_reviews for insert to authenticated
  with check (auth.uid() = owner_id);

drop policy if exists "scibrain_discussion_messages_select_own" on public.scibrain_discussion_messages;
create policy "scibrain_discussion_messages_select_own"
  on public.scibrain_discussion_messages for select to authenticated
  using (auth.uid() = owner_id);

drop policy if exists "scibrain_discussion_messages_insert_own" on public.scibrain_discussion_messages;
create policy "scibrain_discussion_messages_insert_own"
  on public.scibrain_discussion_messages for insert to authenticated
  with check (auth.uid() = owner_id);
