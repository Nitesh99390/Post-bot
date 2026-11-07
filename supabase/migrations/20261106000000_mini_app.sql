-- Post Maker Mini App: complete storage schema (supersedes 20261104000000).
-- Paste into Supabase Dashboard -> SQL Editor and click Run. Safe to re-run.

create table if not exists public.bot_users (
    user_id         bigint primary key,
    first_name      text,
    last_name       text,
    username        text,
    language_code   text,
    photo_url       text,
    is_premium      boolean not null default false,
    posts_created   integer not null default 0,
    deliveries      integer not null default 0,
    default_channel text,
    created_at      timestamptz not null default now(),
    last_seen       timestamptz not null default now()
);
alter table public.bot_users add column if not exists last_name   text;
alter table public.bot_users add column if not exists photo_url   text;
alter table public.bot_users add column if not exists is_premium  boolean not null default false;
alter table public.bot_users add column if not exists deliveries  integer not null default 0;

-- One row per user: the Mini App draft (text, buttons, attached media id).
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

-- Groups and channels the bot can post to.
create table if not exists public.bot_chats (
    chat_id    bigint primary key,
    type       text not null default 'group',
    title      text,
    username   text,
    can_post   boolean not null default true,
    updated_at timestamptz not null default now()
);

-- Which user manages which chat, their default chat and their current selection.
create table if not exists public.user_chats (
    user_id    bigint not null,
    chat_id    bigint not null,
    is_default boolean not null default false,
    selected   boolean not null default false,
    created_at timestamptz not null default now(),
    primary key (user_id, chat_id)
);
create index if not exists user_chats_chat_idx on public.user_chats (chat_id);
-- At most one default chat per user.
create unique index if not exists user_chats_one_default
    on public.user_chats (user_id) where is_default;

alter table public.bot_users    enable row level security;
alter table public.bot_sessions enable row level security;
alter table public.saved_posts  enable row level security;
alter table public.bot_chats    enable row level security;
alter table public.user_chats   enable row level security;

-- The bot server is the only client. It ships with the project's publishable
-- (anon) key by default, so the anon role needs access. Recommended: set
-- SUPABASE_KEY to your sb_secret_ key on the server, then run the "harden"
-- block below so the public key can no longer read or write these tables.
drop policy if exists "bot anon access" on public.bot_users;
drop policy if exists "bot anon access" on public.bot_sessions;
drop policy if exists "bot anon access" on public.saved_posts;
drop policy if exists "bot anon access" on public.bot_chats;
drop policy if exists "bot anon access" on public.user_chats;
create policy "bot anon access" on public.bot_users    for all to anon using (true) with check (true);
create policy "bot anon access" on public.bot_sessions for all to anon using (true) with check (true);
create policy "bot anon access" on public.saved_posts  for all to anon using (true) with check (true);
create policy "bot anon access" on public.bot_chats    for all to anon using (true) with check (true);
create policy "bot anon access" on public.user_chats   for all to anon using (true) with check (true);

grant select, insert, update, delete
    on public.bot_users, public.bot_sessions, public.saved_posts,
       public.bot_chats, public.user_chats to anon;

-- Harden (only after switching the server to a secret key):
-- drop policy "bot anon access" on public.bot_users;
-- drop policy "bot anon access" on public.bot_sessions;
-- drop policy "bot anon access" on public.saved_posts;
-- drop policy "bot anon access" on public.bot_chats;
-- drop policy "bot anon access" on public.user_chats;
-- revoke all on public.bot_users, public.bot_sessions, public.saved_posts,
--               public.bot_chats, public.user_chats from anon;
