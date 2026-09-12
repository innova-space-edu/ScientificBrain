create table if not exists public.scibrain_consents (
  consent_id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  consent_version text not null,
  terms_accepted boolean not null default false,
  ai_use_accepted boolean not null default false,
  data_processing_accepted boolean not null default false,
  cybersecurity_acknowledged boolean not null default false,
  scientific_responsibility_acknowledged boolean not null default false,
  accepted_at timestamptz not null default now(),
  user_agent text,
  created_at timestamptz not null default now(),
  unique (user_id, consent_version)
);

create index if not exists idx_scibrain_consents_user on public.scibrain_consents(user_id, accepted_at desc);

alter table public.scibrain_consents enable row level security;

drop policy if exists "scibrain_consents_owner" on public.scibrain_consents;
create policy "scibrain_consents_owner" on public.scibrain_consents
for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "scibrain_consents_insert_owner" on public.scibrain_consents;
create policy "scibrain_consents_insert_owner" on public.scibrain_consents
for insert to authenticated
with check ((select auth.uid()) = user_id);

revoke all on public.scibrain_consents from anon;
grant select, insert on public.scibrain_consents to authenticated;
