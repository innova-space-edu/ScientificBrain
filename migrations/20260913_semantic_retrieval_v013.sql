create extension if not exists vector with schema extensions;

alter table public.scibrain_paper_chunks
  add column if not exists embedding extensions.vector(768),
  add column if not exists embedding_model text,
  add column if not exists embedding_dimensions integer,
  add column if not exists embedded_at timestamptz;

create index if not exists scibrain_paper_chunks_embedding_hnsw
  on public.scibrain_paper_chunks
  using hnsw (embedding extensions.vector_cosine_ops)
  where embedding is not null;

drop function if exists public.scibrain_hybrid_search_paper_chunks(uuid,text,text,extensions.vector,integer,double precision);

create or replace function public.scibrain_hybrid_search_paper_chunks(
  p_folder_id uuid,
  p_paper_id text,
  p_query text,
  p_query_embedding jsonb,
  p_limit integer default 12,
  p_semantic_weight double precision default 0.72
)
returns table (
  chunk_id uuid,
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
language sql
stable
security invoker
set search_path = public, extensions
as $$
  with params as (
    select case
      when p_query_embedding is null then null::extensions.vector
      else p_query_embedding::text::extensions.vector
    end as query_embedding
  ), scored as (
    select
      c.chunk_id,
      c.chunk_index,
      c.page_start,
      c.page_end,
      c.section_label,
      c.kind,
      c.text,
      case
        when c.embedding is not null and params.query_embedding is not null
          then greatest(0::double precision, 1 - (c.embedding <=> params.query_embedding))
        else 0::double precision
      end as semantic_score,
      case
        when nullif(btrim(coalesce(p_query, '')), '') is null then 0::real
        else ts_rank_cd(c.search_vector, websearch_to_tsquery('simple', p_query))
      end as lexical_score
    from public.scibrain_paper_chunks c
    cross join params
    where c.owner_id = auth.uid()
      and c.folder_id = p_folder_id
      and c.paper_id = p_paper_id
  )
  select
    s.chunk_id,
    s.chunk_index,
    s.page_start,
    s.page_end,
    s.section_label,
    s.kind,
    s.text,
    s.semantic_score,
    s.lexical_score,
    (
      greatest(0::double precision, least(1::double precision, p_semantic_weight)) * s.semantic_score
      + (1 - greatest(0::double precision, least(1::double precision, p_semantic_weight)))
        * least(1::double precision, (s.lexical_score::double precision * 4.0))
    ) as rank
  from scored s
  order by rank desc, s.chunk_index asc
  limit greatest(1, least(coalesce(p_limit, 12), 40));
$$;

grant execute on function public.scibrain_hybrid_search_paper_chunks(uuid,text,text,jsonb,integer,double precision) to authenticated;
