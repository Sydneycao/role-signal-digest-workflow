-- Repair/backfill structured feedback fields after the June feedback-learning migration.
--
-- This intentionally rewrites only derived columns. It preserves raw feedback:
-- id, post_id, post_url, title, feedback_type, note, created_at.

update public.role_feedback
set feedback_category =
  case
    when feedback_type <> 'not_good' then null
    when lower(coalesce(note, '')) ~ '(no longer exists?|expired|broken link)' then 'expired_post'
    when lower(coalesce(note, '')) like '%not a hiring post%' then 'not_hiring_post'
    when lower(coalesce(note, '')) ~ '\m(senior|principal|staff|lead|director)\M'
      or lower(coalesce(note, '')) ~ '\m(10\s*\+?\s*years?|8\s*\+?\s*years?)\M'
      then 'too_senior'
    when replace(lower(coalesce(note, '')), 'u.s.', 'us') ~ '(not in us|not in the us|not in ny|not in sf|\muk\M|\mcanada\M|\mindia\M|\meurope\M|\mmumbai\M|\mlondon\M|\mtexas\M)'
      then 'wrong_location'
    when lower(coalesce(note, '')) like '%duplicate%' then 'duplicate'
    when lower(coalesce(note, '')) ~ '(wrong domain|not relevant domain|irrelevant domain)'
      then 'not_relevant_domain'
    else 'not_relevant_domain'
  end;

update public.role_feedback
set positive_signal_category =
  case
    when feedback_type <> 'good' then null
    when lower(coalesce(title, '') || ' ' || coalesce(note, '')) ~ '(ai agent|ai agents|agentic|llm agent|\mrag\M)'
      then 'strong_ai_agent_match'
    when lower(coalesce(title, '') || ' ' || coalesce(note, '')) ~ '(workflow|automation|internal tools|operations automation)'
      then 'strong_workflow_automation_match'
    when lower(coalesce(title, '') || ' ' || coalesce(note, '')) ~ '(\mgtm\M|go-to-market|sales enablement|\mrevops\M)'
      then 'strong_gtm_ai_match'
    when lower(coalesce(title, '') || ' ' || coalesce(note, '')) ~ '(remote us|us remote|new york|san francisco|bay area)'
      then 'strong_location_match'
    else 'strong_role_match'
  end;

update public.role_feedback rf
set extracted_title_keywords = coalesce((
  select jsonb_agg(distinct term)
  from unnest(array[
    'AI Automation Engineer',
    'AI Agent Engineer',
    'AI Solutions Consultant',
    'AI Solutions Engineer',
    'AI Enablement',
    'AI Builder',
    'Applied AI Engineer',
    'Forward Deployed AI Engineer',
    'TA Operations',
    'Technical Product Manager',
    'AI Product Manager',
    'Data Scientist',
    'ML Engineer',
    'Analytics Engineer',
    'GTM Engineer',
    'Platform Engineer'
  ]) as term
  where lower(coalesce(rf.title, '')) like '%' || lower(term) || '%'
), '[]'::jsonb);

update public.role_feedback rf
set extracted_location_terms = coalesce((
  select jsonb_agg(distinct term)
  from unnest(array[
    'Remote US',
    'US Remote',
    'United States',
    'New York',
    'NYC',
    'San Francisco',
    'Bay Area',
    'California',
    'Texas',
    'UK',
    'United Kingdom',
    'Canada',
    'India',
    'Europe',
    'Mumbai',
    'London',
    'Abu Dhabi'
  ]) as term
  where replace(lower(coalesce(rf.title, '') || ' ' || coalesce(rf.note, '')), 'u.s.', 'us')
    ~ ('\m' || lower(term) || '\M')
), '[]'::jsonb),
extracted_domain_terms = coalesce((
  select jsonb_agg(distinct term)
  from unnest(array[
    'agentic AI',
    'AI Agent',
    'AI agents',
    'LLM',
    'RAG',
    'workflow automation',
    'automation',
    'operations automation',
    'internal enablement',
    'GTM automation',
    'healthcare',
    'healthtech',
    'clinical',
    'claims',
    'life sciences',
    'data products',
    'productivity tooling'
  ]) as term
  where lower(coalesce(rf.title, '') || ' ' || coalesce(rf.note, ''))
    ~ ('\m' || lower(term) || '\M')
), '[]'::jsonb),
extracted_seniority_terms = coalesce((
  select jsonb_agg(distinct term)
  from unnest(array[
    'senior',
    'sr',
    'staff',
    'principal',
    'lead',
    'director',
    'head of',
    'vp',
    '10+ years',
    '8+ years'
  ]) as term
  where lower(coalesce(rf.title, '') || ' ' || coalesce(rf.note, ''))
    ~ ('\m' || replace(lower(term), '+', '\+') || '\M')
), '[]'::jsonb);
