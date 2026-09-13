create table if not exists public.scibrain_corpus_messages (
  message_id uuid primary key default gen_random_uuid(),
  thread_id uuid not null,
  owner_id uuid not null default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  message_role text not null check (message_role in ('user','assistant','system')),
  content text not null,
  citations jsonb not null default '[]'::jsonb,
  retrieval jsonb not null default '{}'::jsonb,
  audit jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists scibrain_corpus_messages_thread_idx
  on public.scibrain_corpus_messages(owner_id, folder_id, thread_id, created_at);

alter table public.scibrain_corpus_messages enable row level security;
drop policy if exists scibrain_corpus_messages_owner_all on public.scibrain_corpus_messages;
create policy scibrain_corpus_messages_owner_all on public.scibrain_corpus_messages
  for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

create table if not exists public.scibrain_literature_watches (
  watch_id uuid primary key default gen_random_uuid(),
  owner_id uuid not null default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  query text not null,
  from_year integer not null default 1900,
  max_results integer not null default 30 check (max_results between 1 and 40),
  include_web boolean not null default true,
  enabled boolean not null default true,
  interval_hours integer not null default 24 check (interval_hours between 1 and 720),
  seen_keys jsonb not null default '[]'::jsonb,
  last_checked_at timestamptz,
  last_new_count integer not null default 0,
  last_result_hash text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists scibrain_literature_watches_due_idx on public.scibrain_literature_watches(enabled, last_checked_at);
create index if not exists scibrain_literature_watches_owner_folder_idx on public.scibrain_literature_watches(owner_id, folder_id, created_at desc);
alter table public.scibrain_literature_watches enable row level security;
drop policy if exists scibrain_literature_watches_owner_all on public.scibrain_literature_watches;
create policy scibrain_literature_watches_owner_all on public.scibrain_literature_watches
  for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

create table if not exists public.scibrain_literature_watch_runs (
  run_id uuid primary key default gen_random_uuid(),
  watch_id uuid not null references public.scibrain_literature_watches(watch_id) on delete cascade,
  owner_id uuid not null default auth.uid(),
  folder_id uuid not null references public.scibrain_folders(folder_id) on delete cascade,
  query text not null,
  result_count integer not null default 0,
  new_count integer not null default 0,
  new_results jsonb not null default '[]'::jsonb,
  sources text[] not null default '{}'::text[],
  errors jsonb not null default '[]'::jsonb,
  result_hash text,
  duration_ms integer,
  created_at timestamptz not null default now()
);

create index if not exists scibrain_literature_watch_runs_watch_idx on public.scibrain_literature_watch_runs(owner_id, folder_id, watch_id, created_at desc);
alter table public.scibrain_literature_watch_runs enable row level security;
drop policy if exists scibrain_literature_watch_runs_owner_all on public.scibrain_literature_watch_runs;
create policy scibrain_literature_watch_runs_owner_all on public.scibrain_literature_watch_runs
  for all to authenticated using (owner_id = auth.uid()) with check (owner_id = auth.uid());

create or replace function public.scibrain_hybrid_search_folder_chunks(
  p_folder_id uuid,
  p_query text,
  p_query_embedding jsonb,
  p_limit integer default 24,
  p_per_paper integer default 4,
  p_semantic_weight double precision default 0.72
)
returns table (
  chunk_id uuid,
  paper_id text,
  title text,
  chunk_index integer,
  page_start integer,
  page_end integer,
  section_label text,
  kind text,
  text text,
  semantic_score double precision,
  lexical_score real,
  rank double precision
)
language sql stable security invoker set search_path = public, extensions
as $$
  with params as (
    select case when p_query_embedding is null then null::extensions.vector else p_query_embedding::text::extensions.vector end as query_embedding
  ), scored as (
    select c.chunk_id, c.paper_id, p.title, c.chunk_index, c.page_start, c.page_end, c.section_label, c.kind, c.text,
      case when c.embedding is not null and params.query_embedding is not null
        then greatest(0::double precision, 1 - (c.embedding <=> params.query_embedding)) else 0::double precision end as semantic_score,
      case when nullif(btrim(coalesce(p_query, '')), '') is null then 0::real
        else ts_rank_cd(c.search_vector, websearch_to_tsquery('simple', p_query)) end as lexical_score
    from public.scibrain_paper_chunks c
    join public.scibrain_folder_papers p on p.folder_id = c.folder_id and p.canonical_id = c.paper_id
    cross join params
    where c.owner_id = auth.uid() and p.owner_id = auth.uid() and c.folder_id = p_folder_id
  ), combined as (
    select s.*,
      (greatest(0::double precision, least(1::double precision, p_semantic_weight)) * s.semantic_score
       + (1 - greatest(0::double precision, least(1::double precision, p_semantic_weight)))
         * least(1::double precision, (s.lexical_score::double precision * 4.0))) as combined_rank
    from scored s
  ), diversified as (
    select c.*, row_number() over (partition by c.paper_id order by c.combined_rank desc, c.chunk_index asc) as paper_rank
    from combined c
  )
  select d.chunk_id, d.paper_id, d.title, d.chunk_index, d.page_start, d.page_end, d.section_label, d.kind, d.text,
    d.semantic_score, d.lexical_score, d.combined_rank
  from diversified d
  where d.paper_rank <= greatest(1, least(coalesce(p_per_paper, 4), 12))
  order by d.combined_rank desc, d.paper_id, d.chunk_index
  limit greatest(1, least(coalesce(p_limit, 24), 80));
$$;

grant execute on function public.scibrain_hybrid_search_folder_chunks(uuid,text,jsonb,integer,integer,double precision) to authenticated;

create or replace function public.scibrain_folder_embedding_stats(p_folder_id uuid)
returns table (paper_count bigint, chunk_count bigint, embedded_chunks bigint, fully_embedded_papers bigint)
language sql stable security invoker set search_path = public, extensions
as $$
  with allowed as (
    select c.paper_id, c.embedding from public.scibrain_paper_chunks c
    where c.owner_id = auth.uid() and c.folder_id = p_folder_id
  ), per_paper as (
    select paper_id, count(*) as total, count(embedding) as embedded from allowed group by paper_id
  )
  select count(*)::bigint, coalesce(sum(total), 0)::bigint, coalesce(sum(embedded), 0)::bigint,
    count(*) filter (where total > 0 and embedded = total)::bigint from per_paper;
$$;

grant execute on function public.scibrain_folder_embedding_stats(uuid) to authenticated;
