create table if not exists public.seen_posts (
  post_id text primary key,
  url text,
  seen_at timestamptz default now()
);
