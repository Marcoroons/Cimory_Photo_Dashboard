-- Photo Review Collaboration Dashboard
-- Full schema, row-level security, helper functions, triggers and RPCs.
-- Apply this whole file once in the Supabase SQL editor.
-- Sections map to TECHNICAL.md parts 5 and 6.

-- ---------------------------------------------------------------------------
-- 5. Data model
-- ---------------------------------------------------------------------------

-- 5.1 Profiles mirror auth.users so we can join display names.
create table if not exists profiles (
  id           uuid primary key references auth.users(id) on delete cascade,
  email        text,
  display_name text,
  created_at   timestamptz not null default now()
);

-- 5.2 Teams and membership.
create table if not exists teams (
  id         uuid primary key default gen_random_uuid(),
  name       text not null,
  owner_id   uuid references profiles(id),
  created_at timestamptz not null default now()
);

create table if not exists team_members (
  team_id    uuid references teams(id) on delete cascade,
  user_id    uuid references profiles(id) on delete cascade,
  role       text not null default 'viewer'
             check (role in ('owner','admin','editor','viewer')),
  created_at timestamptz not null default now(),
  primary key (team_id, user_id)
);

-- 5.3 Invite by code. No email service needed on the free tier.
create table if not exists invitations (
  id         uuid primary key default gen_random_uuid(),
  team_id    uuid references teams(id) on delete cascade,
  email      text,
  role       text not null default 'viewer'
             check (role in ('admin','editor','viewer')),
  code       text unique not null,
  status     text not null default 'pending'
             check (status in ('pending','accepted','revoked')),
  created_by uuid references profiles(id),
  created_at timestamptz not null default now()
);

-- 5.4 Projects belong to a team.
create table if not exists projects (
  id         uuid primary key default gen_random_uuid(),
  team_id    uuid references teams(id) on delete cascade,
  name       text not null,
  slug       text,
  config     jsonb not null default '{}',
  created_at timestamptz not null default now()
);

-- 5.5 Saved column mapping templates per project.
create table if not exists import_templates (
  id         uuid primary key default gen_random_uuid(),
  project_id uuid references projects(id) on delete cascade,
  name       text not null,
  mapping    jsonb not null,
  created_by uuid references profiles(id),
  created_at timestamptz not null default now()
);

-- 5.6 One row per uploaded file, used for idempotency and audit.
create table if not exists ingestion_batches (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid references projects(id) on delete cascade,
  filename       text,
  file_hash      text,
  row_count      int,
  inserted_count int,
  skipped_count  int,
  uploaded_by    uuid references profiles(id),
  created_at     timestamptz not null default now(),
  unique (project_id, file_hash)
);

-- 5.7 The core table. One row per photo submission.
create table if not exists submissions (
  id              uuid primary key default gen_random_uuid(),
  project_id      uuid references projects(id) on delete cascade,
  batch_id        uuid references ingestion_batches(id) on delete set null,
  region          text,
  mcm_id          text,
  center_name     text,
  submission_date date,
  captured_at     timestamptz,
  photo_url       text,
  photo_ref       text,
  latitude        double precision,
  longitude       double precision,
  category        text,
  flags           jsonb not null default '{}',
  is_duplicate    boolean not null default false,
  row_hash        text not null,
  metadata        jsonb not null default '{}',
  created_at      timestamptz not null default now(),
  unique (project_id, row_hash)
);

-- 5.8 One review row per submission, holding the latest decision.
create table if not exists reviews (
  submission_id uuid primary key references submissions(id) on delete cascade,
  project_id    uuid references projects(id) on delete cascade,
  quality       text check (quality in ('good','bad')),
  action        text check (action in ('keep','delete')),
  note          text,
  reviewer_id   uuid references profiles(id),
  version       int not null default 1,
  updated_at    timestamptz not null default now()
);

-- 5.9 Optional soft lock so the UI can show "being reviewed by X".
create table if not exists review_locks (
  submission_id uuid primary key references submissions(id) on delete cascade,
  project_id    uuid references projects(id) on delete cascade,
  locked_by     uuid references profiles(id),
  locked_at     timestamptz not null default now()
);

-- 5.10 Append-only activity feed that drives notifications.
create table if not exists activity_log (
  id            bigint generated always as identity primary key,
  project_id    uuid references projects(id) on delete cascade,
  actor_id      uuid references profiles(id),
  action        text not null,
  submission_id uuid,
  details       jsonb not null default '{}',
  created_at    timestamptz not null default now()
);

-- 5.11 Per-user, per-project read marker for unread counts.
create table if not exists project_last_seen (
  project_id   uuid references projects(id) on delete cascade,
  user_id      uuid references profiles(id) on delete cascade,
  last_seen_at timestamptz not null default now(),
  primary key (project_id, user_id)
);

-- 5.12 Indexes for the common filters.
create index if not exists idx_submissions_region on submissions (project_id, region);
create index if not exists idx_submissions_mcm on submissions (project_id, mcm_id);
create index if not exists idx_submissions_date on submissions (project_id, submission_date);
create index if not exists idx_submissions_dup on submissions (project_id, is_duplicate);
create index if not exists idx_submissions_url on submissions (project_id, photo_url);
create index if not exists idx_reviews_quality on reviews (project_id, quality);
create index if not exists idx_activity_created on activity_log (project_id, created_at desc);

-- ---------------------------------------------------------------------------
-- 6. Row-level security helpers
-- ---------------------------------------------------------------------------

create or replace function is_team_member(_team uuid)
returns boolean language sql security definer stable
set search_path = public as $$
  select exists (
    select 1 from team_members
    where team_id = _team and user_id = auth.uid()
  );
$$;

create or replace function is_team_admin(_team uuid)
returns boolean language sql security definer stable
set search_path = public as $$
  select exists (
    select 1 from team_members
    where team_id = _team and user_id = auth.uid()
      and role in ('owner','admin')
  );
$$;

create or replace function project_role(_project uuid)
returns text language sql security definer stable
set search_path = public as $$
  select tm.role
  from projects p
  join team_members tm on tm.team_id = p.team_id
  where p.id = _project and tm.user_id = auth.uid()
  limit 1;
$$;

-- ---------------------------------------------------------------------------
-- Enable RLS and apply policies.
-- ---------------------------------------------------------------------------

alter table profiles          enable row level security;
alter table teams             enable row level security;
alter table team_members      enable row level security;
alter table invitations       enable row level security;
alter table projects          enable row level security;
alter table import_templates  enable row level security;
alter table ingestion_batches enable row level security;
alter table submissions       enable row level security;
alter table reviews           enable row level security;
alter table review_locks      enable row level security;
alter table activity_log      enable row level security;
alter table project_last_seen enable row level security;

-- profiles: any authenticated user can read (needed for names), own row writable.
drop policy if exists profiles_select on profiles;
create policy profiles_select on profiles
  for select using (auth.uid() is not null);
drop policy if exists profiles_insert on profiles;
create policy profiles_insert on profiles
  for insert with check (id = auth.uid());
drop policy if exists profiles_update on profiles;
create policy profiles_update on profiles
  for update using (id = auth.uid()) with check (id = auth.uid());

-- teams: members read, owner writes. Creation goes through the create_team RPC.
drop policy if exists teams_select on teams;
create policy teams_select on teams
  for select using (is_team_member(id));
drop policy if exists teams_insert on teams;
create policy teams_insert on teams
  for insert with check (owner_id = auth.uid());
drop policy if exists teams_update on teams;
create policy teams_update on teams
  for update using (owner_id = auth.uid()) with check (owner_id = auth.uid());
drop policy if exists teams_delete on teams;
create policy teams_delete on teams
  for delete using (owner_id = auth.uid());

-- team_members: members read, admins manage. Self join goes through redeem_invite RPC.
drop policy if exists team_members_select on team_members;
create policy team_members_select on team_members
  for select using (is_team_member(team_id));
drop policy if exists team_members_insert on team_members;
create policy team_members_insert on team_members
  for insert with check (is_team_admin(team_id));
drop policy if exists team_members_update on team_members;
create policy team_members_update on team_members
  for update using (is_team_admin(team_id)) with check (is_team_admin(team_id));
drop policy if exists team_members_delete on team_members;
create policy team_members_delete on team_members
  for delete using (is_team_admin(team_id));

-- invitations: admins manage. Redeem lookup by code goes through the redeem_invite RPC.
drop policy if exists invitations_select on invitations;
create policy invitations_select on invitations
  for select using (is_team_admin(team_id));
drop policy if exists invitations_write on invitations;
create policy invitations_write on invitations
  for all using (is_team_admin(team_id)) with check (is_team_admin(team_id));

-- projects: members read, admins manage.
drop policy if exists projects_select on projects;
create policy projects_select on projects
  for select using (is_team_member(team_id));
drop policy if exists projects_insert on projects;
create policy projects_insert on projects
  for insert with check (is_team_admin(team_id));
drop policy if exists projects_update on projects;
create policy projects_update on projects
  for update using (is_team_admin(team_id)) with check (is_team_admin(team_id));
drop policy if exists projects_delete on projects;
create policy projects_delete on projects
  for delete using (is_team_admin(team_id));

-- The project-scoped tables all share the same shape:
-- members read, editors and above write.
drop policy if exists import_templates_select on import_templates;
create policy import_templates_select on import_templates
  for select using (project_role(project_id) is not null);
drop policy if exists import_templates_write on import_templates;
create policy import_templates_write on import_templates
  for all using (project_role(project_id) in ('owner','admin','editor'))
  with check (project_role(project_id) in ('owner','admin','editor'));

drop policy if exists ingestion_batches_select on ingestion_batches;
create policy ingestion_batches_select on ingestion_batches
  for select using (project_role(project_id) is not null);
drop policy if exists ingestion_batches_write on ingestion_batches;
create policy ingestion_batches_write on ingestion_batches
  for all using (project_role(project_id) in ('owner','admin','editor'))
  with check (project_role(project_id) in ('owner','admin','editor'));

drop policy if exists submissions_select on submissions;
create policy submissions_select on submissions
  for select using (project_role(project_id) is not null);
drop policy if exists submissions_write on submissions;
create policy submissions_write on submissions
  for all using (project_role(project_id) in ('owner','admin','editor'))
  with check (project_role(project_id) in ('owner','admin','editor'));

drop policy if exists reviews_select on reviews;
create policy reviews_select on reviews
  for select using (project_role(project_id) is not null);
drop policy if exists reviews_write on reviews;
create policy reviews_write on reviews
  for all using (project_role(project_id) in ('owner','admin','editor'))
  with check (project_role(project_id) in ('owner','admin','editor'));

drop policy if exists review_locks_select on review_locks;
create policy review_locks_select on review_locks
  for select using (project_role(project_id) is not null);
drop policy if exists review_locks_write on review_locks;
create policy review_locks_write on review_locks
  for all using (project_role(project_id) in ('owner','admin','editor'))
  with check (project_role(project_id) in ('owner','admin','editor'));

drop policy if exists activity_log_select on activity_log;
create policy activity_log_select on activity_log
  for select using (project_role(project_id) is not null);
drop policy if exists activity_log_write on activity_log;
create policy activity_log_write on activity_log
  for all using (project_role(project_id) in ('owner','admin','editor'))
  with check (project_role(project_id) in ('owner','admin','editor'));

-- project_last_seen: a user only ever reads and writes their own marker.
drop policy if exists project_last_seen_all on project_last_seen;
create policy project_last_seen_all on project_last_seen
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());

-- ---------------------------------------------------------------------------
-- 7. Profile creation on sign up, via a trigger for reliability.
-- ---------------------------------------------------------------------------

create or replace function public.handle_new_user()
returns trigger language plpgsql security definer
set search_path = public as $$
begin
  insert into public.profiles (id, email, display_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1))
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- 8. Team bootstrap and invite redemption, security definer so the app
--    never needs the service role key.
-- ---------------------------------------------------------------------------

-- Create a team and make the caller its owner, atomically.
create or replace function public.create_team(_name text)
returns uuid language plpgsql security definer
set search_path = public as $$
declare _team uuid;
begin
  if auth.uid() is null then
    raise exception 'not authenticated';
  end if;
  insert into teams (name, owner_id) values (_name, auth.uid())
    returning id into _team;
  insert into team_members (team_id, user_id, role)
    values (_team, auth.uid(), 'owner')
    on conflict (team_id, user_id) do nothing;
  return _team;
end;
$$;

-- Redeem an invite code and join the team with the invited role.
create or replace function public.redeem_invite(_code text)
returns uuid language plpgsql security definer
set search_path = public as $$
declare inv invitations;
begin
  if auth.uid() is null then
    raise exception 'not authenticated';
  end if;
  select * into inv from invitations
    where code = _code and status = 'pending' limit 1;
  if inv.id is null then
    raise exception 'invalid or already used code';
  end if;
  insert into team_members (team_id, user_id, role)
    values (inv.team_id, auth.uid(), inv.role)
    on conflict (team_id, user_id) do update set role = excluded.role;
  update invitations set status = 'accepted' where id = inv.id;
  return inv.team_id;
end;
$$;

grant execute on function public.create_team(text)   to authenticated;
grant execute on function public.redeem_invite(text)  to authenticated;
grant execute on function public.is_team_member(uuid) to authenticated;
grant execute on function public.is_team_admin(uuid)  to authenticated;
grant execute on function public.project_role(uuid)   to authenticated;
