create table if not exists public.seen_posts (
  post_id text primary key,
  url text,
  seen_at timestamptz default now()
);

create table if not exists public.role_feedback (
  id uuid primary key default gen_random_uuid(),
  post_id text not null,
  post_url text,
  title text,
  feedback_type text not null check (feedback_type in ('good', 'not_good')),
  note text,
  created_at timestamptz default now()
);

create index if not exists role_feedback_post_id_idx
  on public.role_feedback (post_id);

create index if not exists role_feedback_created_at_idx
  on public.role_feedback (created_at desc);

create table if not exists public.apify_query_performance (
  query text primary key,
  posts_returned integer not null default 0,
  unique_posts integer not null default 0,
  valid_hiring_signals integer not null default 0,
  high_fit_signals integer not null default 0,
  duplicate_rate double precision not null default 0,
  last_run_at timestamptz,
  updated_at timestamptz default now()
);

create index if not exists apify_query_performance_last_run_at_idx
  on public.apify_query_performance (last_run_at desc);
