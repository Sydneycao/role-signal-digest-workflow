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
