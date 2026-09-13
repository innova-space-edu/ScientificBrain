-- Unify the legacy study-chat schema and the collaborative research-chat schema.
-- Safe for both upgrade paths: old installations and fresh installations.
alter table public.scibrain_discussion_messages
  add column if not exists study_id uuid references public.scibrain_studies(study_id) on delete cascade,
  add column if not exists speaker text,
  add column if not exists agent_role text,
  add column if not exists source_refs jsonb not null default '[]'::jsonb,
  add column if not exists document_id uuid references public.scibrain_research_documents(document_id) on delete cascade,
  add column if not exists message_role text,
  add column if not exists agent_id text,
  add column if not exists section_key text,
  add column if not exists evidence_refs jsonb not null default '[]'::jsonb;

update public.scibrain_discussion_messages
set message_role = coalesce(message_role, speaker),
    agent_id = coalesce(agent_id, agent_role),
    evidence_refs = coalesce(evidence_refs, source_refs, '[]'::jsonb)
where message_role is null or agent_id is null or evidence_refs is null;

alter table public.scibrain_discussion_messages alter column study_id drop not null;
alter table public.scibrain_discussion_messages alter column speaker drop not null;
alter table public.scibrain_discussion_messages drop constraint if exists scibrain_discussion_messages_message_role_check;
alter table public.scibrain_discussion_messages add constraint scibrain_discussion_messages_message_role_check
  check (message_role is null or message_role in ('user','agent','system'));

create index if not exists idx_scibrain_discussion_messages_study_id on public.scibrain_discussion_messages(study_id);
create index if not exists idx_scibrain_discussion_messages_document_id on public.scibrain_discussion_messages(document_id);
create index if not exists idx_scibrain_discussion_messages_owner_folder_created on public.scibrain_discussion_messages(owner_id, folder_id, created_at desc);

revoke all on public.scibrain_projects, public.scibrain_states, public.scibrain_artifacts,
  public.scibrain_jobs, public.scibrain_studies, public.scibrain_study_reviews from anon;
grant select, insert, update, delete on public.scibrain_discussion_messages to authenticated;
