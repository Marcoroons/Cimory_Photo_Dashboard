-- Give editors admin-like powers except managing members.
-- Run this once in the Supabase SQL editor if you already applied 0001.
-- Editors can create and edit projects and manage invite codes. Changing member
-- roles, removing members, and deleting projects stay with owners and admins.

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

-- Projects: editors can create and edit, admins still delete.
drop policy if exists projects_insert on projects;
create policy projects_insert on projects
  for insert with check (is_team_editor(team_id));
drop policy if exists projects_update on projects;
create policy projects_update on projects
  for update using (is_team_editor(team_id)) with check (is_team_editor(team_id));

-- Invitations: editors can manage them.
drop policy if exists invitations_select on invitations;
create policy invitations_select on invitations
  for select using (is_team_editor(team_id));
drop policy if exists invitations_write on invitations;
create policy invitations_write on invitations
  for all using (is_team_editor(team_id)) with check (is_team_editor(team_id));
