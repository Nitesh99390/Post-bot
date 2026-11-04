-- Post Maker Bot storage.
-- Run once in Supabase Dashboard -> SQL Editor (or `supabase db push`).
-- Safe to re-run.

create table if not exists public.bot_users (
    user_id         bigint primary key,
    first_name      text,
    username        text,
    language_code   text,
    posts_created   integer not null default 0,
    default_channel text,
    created_at      timestamptz not null default now(),
    last_seen       timestamptz not null default now()
);

create table if not exists public.bot_sessions (
    user_id    bigint primary key,
    data       jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists public.saved_posts (
    id         bigint generated always as identity primary key,
    user_id    bigint not null,
    name       text not null check (char_length(name) between 1 and 40),
    post       jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists saved_posts_user_idx
    on public.saved_posts (user_id, updated_at desc);

-- Row Level Security is always on. The bot is the only client of these tables.
alter table public.bot_users    enable row level security;
alter table public.bot_sessions enable row level security;
alter table public.saved_posts  enable row level security;

-- The bot ships with the project's publishable (anon) key, so the anon role
-- needs access. For stronger isolation, set SUPABASE_KEY to a sb_secret_ /
-- service_role key on Render and run the "harden" block at the bottom.
drop policy if exists "bot anon access" on public.bot_users;
drop policy if exists "bot anon access" on public.bot_sessions;
drop policy if exists "bot anon access" on public.saved_posts;
create policy "bot anon access" on public.bot_users    for all to anon using (true) with check (true);
create policy "bot anon access" on public.bot_sessions for all to anon using (true) with check (true);
create policy "bot anon access" on public.saved_posts  for all to anon using (true) with check (true);

grant select, insert, update, delete on public.bot_users, public.bot_sessions, public.saved_posts to anon;

-- Harden (optional, only after switching the bot to a secret key):
-- drop policy "bot anon access" on public.bot_users;
-- drop policy "bot anon access" on public.bot_sessions;
-- drop policy "bot anon access" on public.saved_posts;
-- revoke all on public.bot_users, public.bot_sessions, public.saved_posts from anon;
