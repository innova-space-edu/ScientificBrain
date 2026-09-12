create extension if not exists pgcrypto;

create table if not exists public.scibrain_projects (
  project_id text primary key,
  title text not null,
  discipline text not null,
  definition jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.scibrain_states (
  session_id text primary key,
  project_id text references public.scibrain_projects(project_id) on delete set null,
  question text not null,
  stage text not null,
  state jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.scibrain_papers (
  canonical_id text primary key,
  review_depth text not null default 'metadata_verified',
  record jsonb not null,
  analysis jsonb,
  critique jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists public.scibrain_evidence (
  evidence_id text primary key,
  paper_id text not null references public.scibrain_papers(canonical_id) on delete cascade,
  claim_id text,
  epistemic_status text,
  evidence jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.scibrain_artifacts (
  artifact_id text primary key,
  session_id text references public.scibrain_states(session_id) on delete cascade,
  artifact_type text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_scibrain_states_project on public.scibrain_states(project_id);
create index if not exists idx_scibrain_states_stage on public.scibrain_states(stage);
create index if not exists idx_scibrain_evidence_paper on public.scibrain_evidence(paper_id);
create index if not exists idx_scibrain_artifacts_session on public.scibrain_artifacts(session_id);

alter table public.scibrain_projects enable row level security;
alter table public.scibrain_states enable row level security;
alter table public.scibrain_papers enable row level security;
alter table public.scibrain_evidence enable row level security;
alter table public.scibrain_artifacts enable row level security;

-- No public RLS policies are created intentionally. ScientificBrain server-side code uses the
-- Supabase service-role key. Never expose SUPABASE_SERVICE_ROLE_KEY to browser/client code.
