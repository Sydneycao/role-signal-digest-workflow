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
  feedback_category text check (
    feedback_category in (
      'too_senior',
      'wrong_location',
      'not_hiring_post',
      'expired_post',
      'not_relevant_domain',
      'duplicate',
      'other'
    )
  ),
  positive_signal_category text check (
    positive_signal_category in (
      'strong_role_match',
      'strong_domain_match',
      'strong_ai_agent_match',
      'strong_workflow_automation_match',
      'strong_gtm_ai_match',
      'strong_location_match',
      'acceptable_seniority',
      'other'
    )
  ),
  extracted_title_keywords jsonb not null default '[]'::jsonb,
  extracted_location_terms jsonb not null default '[]'::jsonb,
  extracted_domain_terms jsonb not null default '[]'::jsonb,
  extracted_seniority_terms jsonb not null default '[]'::jsonb,
  created_at timestamptz default now()
);

create index if not exists role_feedback_post_id_idx
  on public.role_feedback (post_id);

alter table public.role_feedback
  add column if not exists feedback_category text,
  add column if not exists positive_signal_category text,
  add column if not exists extracted_title_keywords jsonb not null default '[]'::jsonb,
  add column if not exists extracted_location_terms jsonb not null default '[]'::jsonb,
  add column if not exists extracted_domain_terms jsonb not null default '[]'::jsonb,
  add column if not exists extracted_seniority_terms jsonb not null default '[]'::jsonb;

create index if not exists role_feedback_created_at_idx
  on public.role_feedback (created_at desc);

create index if not exists role_feedback_feedback_category_idx
  on public.role_feedback (feedback_category);

create index if not exists role_feedback_positive_signal_category_idx
  on public.role_feedback (positive_signal_category);

create table if not exists public.feedback_filter_config (
  key text primary key default 'active',
  config jsonb not null default '{}'::jsonb,
  updated_at timestamptz default now()
);

insert into public.feedback_filter_config (key, config)
values (
  'active',
  '{
    "allowed_locations": ["US", "Remote US", "New York", "San Francisco"],
    "blocked_locations": [],
    "blocked_seniority_keywords": [],
    "max_years_experience": 6,
    "require_hiring_signal": false,
    "positive_title_boost_keywords": ["AI Builder", "AI Automation Engineer", "AI Agent Engineer", "AI Enablement", "AI Solutions Consultant"],
    "positive_domain_boost_keywords": ["agentic AI", "workflow automation", "AI agents", "internal enablement", "GTM automation"],
    "positive_workflow_boost_keywords": ["workflow automation", "operations automation", "process automation", "internal tools"],
    "positive_agent_boost_keywords": ["AI Agent", "AI agents", "agentic AI", "LLM agent"],
    "positive_location_boost_terms": ["US", "Remote US", "New York", "San Francisco"],
    "acceptable_seniority_keywords": ["Associate", "Junior", "Entry", "Early Career", "Mid-level", "II"]
  }'::jsonb
)
on conflict (key) do nothing;

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
