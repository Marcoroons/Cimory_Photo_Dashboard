-- Let a user create their own teams and leave teams.
-- create_team already exists from 0001. This adds leave_team.
-- Run this once in the Supabase SQL editor if you already applied 0001.

create or replace function public.leave_team(_team uuid)
returns void language plpgsql security definer
set search_path = public as $$
begin
  if auth.uid() is null then
    raise exception 'not authenticated';
  end if;
  if exists (
        select 1 from team_members
        where team_id = _team and user_id = auth.uid() and role = 'owner')
     and (select count(*) from team_members
          where team_id = _team and role = 'owner') <= 1 then
    raise exception 'The only owner cannot leave. Make someone else an owner first.';
  end if;
  delete from team_members where team_id = _team and user_id = auth.uid();
end;
$$;

grant execute on function public.leave_team(uuid) to authenticated;
