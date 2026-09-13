create or replace function public.scibrain_upsert_chunk_embeddings(
  p_folder_id uuid,
  p_paper_id text,
  p_model text,
  p_dimensions integer,
  p_items jsonb
)
returns integer
language plpgsql
security invoker
set search_path = public, extensions
as $$
declare
  item jsonb;
  changed integer := 0;
begin
  if p_dimensions <> 768 then
    raise exception 'embedding dimension must be 768';
  end if;
  for item in select value from jsonb_array_elements(coalesce(p_items, '[]'::jsonb))
  loop
    update public.scibrain_paper_chunks c
       set embedding = (item->'embedding')::text::extensions.vector,
           embedding_model = p_model,
           embedding_dimensions = p_dimensions,
           embedded_at = now(),
           updated_at = now()
     where c.chunk_id = (item->>'chunk_id')::uuid
       and c.owner_id = auth.uid()
       and c.folder_id = p_folder_id
       and c.paper_id = p_paper_id;
    changed := changed + case when found then 1 else 0 end;
  end loop;
  return changed;
end;
$$;

grant execute on function public.scibrain_upsert_chunk_embeddings(uuid,text,text,integer,jsonb) to authenticated;
