-- ScientificBrain runtime/security optimization.
-- Safe to re-run: indexes use IF NOT EXISTS and policies are recreated by stable name.

-- This helper is administrative and must not be callable through the public REST API.
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;

-- Cover foreign keys that are frequently used for folder-scoped deletes, joins and RLS queries.
create index if not exists idx_scibrain_folders_parent_id on public.scibrain_folders(parent_id);
create index if not exists idx_scibrain_projects_folder_id on public.scibrain_projects(folder_id);
create index if not exists idx_scibrain_states_folder_id on public.scibrain_states(folder_id);
create index if not exists idx_scibrain_jobs_folder_id on public.scibrain_jobs(folder_id);
create index if not exists idx_scibrain_folder_papers_folder_id on public.scibrain_folder_papers(folder_id);
create index if not exists idx_scibrain_folder_papers_project_id on public.scibrain_folder_papers(project_id);
create index if not exists idx_scibrain_research_searches_folder_id on public.scibrain_research_searches(folder_id);
create index if not exists idx_scibrain_research_searches_project_id on public.scibrain_research_searches(project_id);
create index if not exists idx_scibrain_graph_nodes_folder_id on public.scibrain_graph_nodes(folder_id);
create index if not exists idx_scibrain_graph_edges_folder_id on public.scibrain_graph_edges(folder_id);
create index if not exists idx_scibrain_contradictions_folder_id on public.scibrain_contradictions(folder_id);
create index if not exists idx_scibrain_evidence_lineage_folder_id on public.scibrain_evidence_lineage(folder_id);
create index if not exists idx_scibrain_hypothesis_competitions_folder_id on public.scibrain_hypothesis_competitions(folder_id);
create index if not exists idx_scibrain_research_documents_folder_id on public.scibrain_research_documents(folder_id);
create index if not exists idx_scibrain_research_documents_project_id on public.scibrain_research_documents(project_id);
create index if not exists idx_scibrain_studies_folder_id on public.scibrain_studies(folder_id);
create index if not exists idx_scibrain_study_reviews_folder_id on public.scibrain_study_reviews(folder_id);
create index if not exists idx_scibrain_study_reviews_study_id on public.scibrain_study_reviews(study_id);
create index if not exists idx_scibrain_discussion_messages_folder_id on public.scibrain_discussion_messages(folder_id);
create index if not exists idx_scibrain_discussion_messages_study_id on public.scibrain_discussion_messages(study_id);

-- Remove redundant permissive policies: the owner policy already covers SELECT/INSERT/UPDATE/DELETE.
drop policy if exists scibrain_discussion_messages_insert_own on public.scibrain_discussion_messages;
drop policy if exists scibrain_discussion_messages_select_own on public.scibrain_discussion_messages;

-- Recreate study policies using an init-plan auth lookup instead of evaluating auth.uid() per row.
drop policy if exists scibrain_studies_select_own on public.scibrain_studies;
create policy scibrain_studies_select_own on public.scibrain_studies
for select to authenticated
using ((select auth.uid()) = owner_id);

drop policy if exists scibrain_studies_insert_own on public.scibrain_studies;
create policy scibrain_studies_insert_own on public.scibrain_studies
for insert to authenticated
with check ((select auth.uid()) = owner_id);

drop policy if exists scibrain_studies_update_own on public.scibrain_studies;
create policy scibrain_studies_update_own on public.scibrain_studies
for update to authenticated
using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists scibrain_studies_delete_own on public.scibrain_studies;
create policy scibrain_studies_delete_own on public.scibrain_studies
for delete to authenticated
using ((select auth.uid()) = owner_id);

drop policy if exists scibrain_study_reviews_select_own on public.scibrain_study_reviews;
create policy scibrain_study_reviews_select_own on public.scibrain_study_reviews
for select to authenticated
using ((select auth.uid()) = owner_id);

drop policy if exists scibrain_study_reviews_insert_own on public.scibrain_study_reviews;
create policy scibrain_study_reviews_insert_own on public.scibrain_study_reviews
for insert to authenticated
with check ((select auth.uid()) = owner_id);
