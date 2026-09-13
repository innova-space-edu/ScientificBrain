-- ScientificBrain security hardening applied to cwbnvukerekgcedcyydd.

create or replace function public.scibrain_set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- New-user profile creation is trigger-only; browser roles must not call it as RPC.
revoke all on function public.scibrain_handle_new_user() from public;
revoke all on function public.scibrain_handle_new_user() from anon;
revoke all on function public.scibrain_handle_new_user() from authenticated;

-- Legacy global paper/evidence tables are server-only. User-facing literature lives in
-- scibrain_folder_papers under owner_id/auth.uid() RLS.
revoke all on public.scibrain_papers from anon, authenticated;
revoke all on public.scibrain_evidence from anon, authenticated;
