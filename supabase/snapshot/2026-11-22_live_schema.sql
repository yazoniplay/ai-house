-- REFERENCE ONLY. Do not run on the live project.
-- Rebuilt from the live catalog of project ccdykioxztegxonuyvwb on 2026-11-22.
-- The original migration files for the first four migrations were not available;
-- this shows what they produced.

-- Tables (RLS enabled on all, no RLS policies defined: only the service role can read or write)

create table public.rooms (
  id text primary key,
  name text,
  active boolean default false,
  daily_cap_usd numeric default 0,
  created_at timestamptz default now()
);

create table public.agents (
  id text primary key,
  room_id text not null references public.rooms(id),
  role text,
  model_tier text,
  system_prompt text,
  tools jsonb default '[]'::jsonb,
  active boolean default false,
  created_at timestamptz default now(),
  description text,
  capabilities jsonb default '{}'::jsonb
);

create table public.tasks (
  id uuid primary key default gen_random_uuid(),
  goal text,
  room_id text not null references public.rooms(id),
  agent_id text references public.agents(id),
  status text not null default 'pending' check (status = any (array['pending','running','waiting_approval','done','failed','blocked'])),
  instruction text not null,
  depends_on uuid[] default '{}'::uuid[],
  input jsonb,
  output jsonb,
  cost_usd numeric not null default 0,
  error text,
  created_at timestamptz default now(),
  started_at timestamptz,
  finished_at timestamptz,
  not_before timestamptz,
  attempts integer not null default 0,
  review jsonb
);

create table public.approvals (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks(id),
  reason text,
  decision text not null default 'pending' check (decision = any (array['pending','approved','rejected'])),
  decided_at timestamptz,
  created_at timestamptz default now()
);

create table public.logs (
  id bigserial primary key,
  task_id uuid references public.tasks(id),
  event text not null,
  detail jsonb,
  created_at timestamptz default now()
);

create table public.lessons (
  id bigserial primary key,
  goal text,
  room_id text references public.rooms(id),
  outcome text not null check (outcome = any (array['success','partial','failed','abandoned'])),
  lesson text not null,
  created_at timestamptz default now()
);

create index tasks_status_idx on public.tasks (status);
create index lessons_room_idx on public.lessons (room_id, created_at desc);

-- Functions

create or replace function public.claim_next_task()
returns setof public.tasks
language plpgsql
security definer
set search_path to 'public'
as $$
declare t tasks;
begin
  select * into t from tasks
   where status = 'pending'
     and (not_before is null or not_before <= now())
     and not exists (
       select 1 from unnest(depends_on) d
       join tasks x on x.id = d
       where x.status <> 'done')
   order by created_at
   for update skip locked
   limit 1;
  if not found then return; end if;
  update tasks set status = 'running', started_at = now()
   where id = t.id returning * into t;
  return next t;
end $$;

create or replace function public.decide_approval(p_task uuid, p_approve boolean)
returns void
language plpgsql
security definer
set search_path to 'public'
as $$
begin
  update approvals
     set decision = case when p_approve then 'approved' else 'rejected' end,
         decided_at = now()
   where task_id = p_task and decision = 'pending';
  update tasks
     set status = case when p_approve then 'pending' else 'blocked' end,
         error = case when p_approve then null else 'rejected by owner' end
   where id = p_task and status = 'waiting_approval';
end $$;

-- review_gate_retry_trigger: see supabase/migrations/20261122090000_review_gate_retry_trigger.sql
