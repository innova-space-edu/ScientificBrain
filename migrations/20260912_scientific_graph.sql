-- ScientificBrain v0.7 scientific knowledge graph
-- User and folder scoped; all browser access remains governed by Supabase Auth + RLS.

create table if not exists public.scibrain_graph_nodes (
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  node_id text not null,
  node_type text not null,
  label text not null,
  paper_id text,
  claim_id text,
  evidence_id text,
  epistemic_state text not null default 'unresolved',
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_id, folder_id, node_id)
);

create index if not exists idx_scibrain_graph_nodes_folder_type
  on public.scibrain_graph_nodes(owner_id, folder_id, node_type);
create index if not exists idx_scibrain_graph_nodes_paper
  on public.scibrain_graph_nodes(owner_id, folder_id, paper_id)
  where paper_id is not null;
create index if not exists idx_scibrain_graph_nodes_claim
  on public.scibrain_graph_nodes(owner_id, folder_id, claim_id)
  where claim_id is not null;

create table if not exists public.scibrain_graph_edges (
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  edge_id text not null,
  source_node_id text not null,
  target_node_id text not null,
  relation text not null,
  confidence double precision not null default 1.0 check (confidence between 0 and 1),
  rationale text,
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_id, folder_id, edge_id)
);

create index if not exists idx_scibrain_graph_edges_source
  on public.scibrain_graph_edges(owner_id, folder_id, source_node_id, relation);
create index if not exists idx_scibrain_graph_edges_target
  on public.scibrain_graph_edges(owner_id, folder_id, target_node_id, relation);

create table if not exists public.scibrain_contradictions (
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  contradiction_id text not null,
  claim_a_id text not null,
  claim_b_id text not null,
  contradiction_type text not null,
  summary text not null,
  regime_difference text,
  possible_explanation text,
  discriminating_observables jsonb not null default '[]'::jsonb,
  required_test text,
  confidence double precision not null default 0.5 check (confidence between 0 and 1),
  status text not null default 'candidate',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_id, folder_id, contradiction_id)
);

create index if not exists idx_scibrain_contradictions_folder
  on public.scibrain_contradictions(owner_id, folder_id, status, confidence desc);

create table if not exists public.scibrain_hypothesis_competitions (
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  competition_id text not null,
  question text not null,
  contradiction_ids jsonb not null default '[]'::jsonb,
  hypotheses jsonb not null default '[]'::jsonb,
  decision_needed text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_id, folder_id, competition_id)
);

create table if not exists public.scibrain_evidence_lineage (
  owner_id uuid not null references auth.users(id) on delete cascade default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  lineage_id text not null,
  source_evidence_id text not null,
  target_evidence_id text not null,
  lineage_type text not null,
  confidence double precision not null default 0.5 check (confidence between 0 and 1),
  rationale text,
  status text not null default 'candidate',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (owner_id, folder_id, lineage_id)
);

create index if not exists idx_scibrain_evidence_lineage_folder
  on public.scibrain_evidence_lineage(owner_id, folder_id, lineage_type);

-- Keep timestamps fresh.
drop trigger if exists scibrain_graph_nodes_updated_at on public.scibrain_graph_nodes;
create trigger scibrain_graph_nodes_updated_at before update on public.scibrain_graph_nodes
for each row execute function public.scibrain_set_updated_at();
drop trigger if exists scibrain_graph_edges_updated_at on public.scibrain_graph_edges;
create trigger scibrain_graph_edges_updated_at before update on public.scibrain_graph_edges
for each row execute function public.scibrain_set_updated_at();
drop trigger if exists scibrain_contradictions_updated_at on public.scibrain_contradictions;
create trigger scibrain_contradictions_updated_at before update on public.scibrain_contradictions
for each row execute function public.scibrain_set_updated_at();
drop trigger if exists scibrain_hypothesis_competitions_updated_at on public.scibrain_hypothesis_competitions;
create trigger scibrain_hypothesis_competitions_updated_at before update on public.scibrain_hypothesis_competitions
for each row execute function public.scibrain_set_updated_at();
drop trigger if exists scibrain_evidence_lineage_updated_at on public.scibrain_evidence_lineage;
create trigger scibrain_evidence_lineage_updated_at before update on public.scibrain_evidence_lineage
for each row execute function public.scibrain_set_updated_at();

-- RLS
alter table public.scibrain_graph_nodes enable row level security;
alter table public.scibrain_graph_edges enable row level security;
alter table public.scibrain_contradictions enable row level security;
alter table public.scibrain_hypothesis_competitions enable row level security;
alter table public.scibrain_evidence_lineage enable row level security;

revoke all on public.scibrain_graph_nodes, public.scibrain_graph_edges,
  public.scibrain_contradictions, public.scibrain_hypothesis_competitions,
  public.scibrain_evidence_lineage from anon;

grant select, insert, update, delete on public.scibrain_graph_nodes, public.scibrain_graph_edges,
  public.scibrain_contradictions, public.scibrain_hypothesis_competitions,
  public.scibrain_evidence_lineage to authenticated;

drop policy if exists "scibrain_graph_nodes_owner" on public.scibrain_graph_nodes;
create policy "scibrain_graph_nodes_owner" on public.scibrain_graph_nodes
for all to authenticated using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_graph_edges_owner" on public.scibrain_graph_edges;
create policy "scibrain_graph_edges_owner" on public.scibrain_graph_edges
for all to authenticated using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_contradictions_owner" on public.scibrain_contradictions;
create policy "scibrain_contradictions_owner" on public.scibrain_contradictions
for all to authenticated using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_hypothesis_competitions_owner" on public.scibrain_hypothesis_competitions;
create policy "scibrain_hypothesis_competitions_owner" on public.scibrain_hypothesis_competitions
for all to authenticated using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);

drop policy if exists "scibrain_evidence_lineage_owner" on public.scibrain_evidence_lineage;
create policy "scibrain_evidence_lineage_owner" on public.scibrain_evidence_lineage
for all to authenticated using ((select auth.uid()) = owner_id)
with check ((select auth.uid()) = owner_id);
