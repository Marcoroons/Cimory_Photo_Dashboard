-- Let editors create projects, not just admins.
-- Run this once in the Supabase SQL editor if you already applied 0001.
-- Update and delete on projects stay admin only.

create or replace function is_team_editor(_team uuid)
returns boolean language sql security definer stable
set search_path = public as $$
  select exists (
    select 1 from team_members
    where team_id = _team and user_id = auth.uid()
      and role in ('owner','admin','editor')
  );
$$;

grant execute on function public.is_team_editor(uuid) to authenticated;

drop policy if exists projects_insert on projects;
create policy projects_insert on projects
  for insert with check (is_team_editor(team_id));
