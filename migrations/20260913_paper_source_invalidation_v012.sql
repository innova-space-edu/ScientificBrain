create or replace function public.scibrain_invalidate_paper_source_before()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if old.storage_path is distinct from new.storage_path
     or old.pdf_url is distinct from new.pdf_url
     or old.original_filename is distinct from new.original_filename then
    new.review_depth := 'metadata_verified';
    new.analysis := null;
    new.critique := null;
    new.specialist_reviews := '[]'::jsonb;
  end if;
  return new;
end;
$$;

drop trigger if exists scibrain_invalidate_paper_source_before on public.scibrain_folder_papers;
create trigger scibrain_invalidate_paper_source_before
before update of storage_path, pdf_url, original_filename on public.scibrain_folder_papers
for each row execute function public.scibrain_invalidate_paper_source_before();

create or replace function public.scibrain_invalidate_paper_memory_after()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if old.storage_path is distinct from new.storage_path
     or old.pdf_url is distinct from new.pdf_url
     or old.original_filename is distinct from new.original_filename then
    delete from public.scibrain_paper_assets
      where owner_id = new.owner_id and folder_id = new.folder_id and paper_id = new.canonical_id;
    delete from public.scibrain_paper_chunks
      where owner_id = new.owner_id and folder_id = new.folder_id and paper_id = new.canonical_id;
    delete from public.scibrain_paper_memory
      where owner_id = new.owner_id and folder_id = new.folder_id and paper_id = new.canonical_id;
  end if;
  return new;
end;
$$;

drop trigger if exists scibrain_invalidate_paper_memory_after on public.scibrain_folder_papers;
create trigger scibrain_invalidate_paper_memory_after
after update of storage_path, pdf_url, original_filename on public.scibrain_folder_papers
for each row execute function public.scibrain_invalidate_paper_memory_after();
