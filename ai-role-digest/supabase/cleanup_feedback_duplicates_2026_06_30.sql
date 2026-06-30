-- Clean up accidental/duplicate role feedback and add guardrails.
--
-- Run this once in Supabase SQL Editor before re-running schema.sql on an
-- existing database with historical role_feedback rows.

begin;

-- Recompute derived negative categories with the current classifier rules.
update public.role_feedback
set feedback_category =
  case
    when feedback_type <> 'not_good' then null
    when lower(coalesce(note, '')) ~ '(no longer exists?|expired|broken link)' then 'expired_post'
    when lower(coalesce(note, '')) like '%not a hiring post%' then 'not_hiring_post'
    when lower(coalesce(note, '')) ~ '\m(senior|principal|staff|lead|director)\M'
      or lower(coalesce(note, '')) ~ '\m(10\s*\+?\s*years?|8\s*\+?\s*years?)\M'
      then 'too_senior'
    when lower(replace(coalesce(note, ''), 'u.s.', 'us')) ~
      '(not in us|not in the us|not in ny|not in sf|\muk\M|\mcanada\M|\mindia\M|\meurope\M|\mmumbai\M|\mlondon\M|\mtexas\M)'
      then 'wrong_location'
    when lower(coalesce(note, '')) like '%duplicate%' then 'duplicate'
    when lower(coalesce(note, '')) ~ '(wrong domain|not relevant domain|irrelevant domain)'
      then 'not_relevant_domain'
    else 'not_relevant_domain'
  end;

-- Recompute derived positive categories with the current classifier rules.
update public.role_feedback
set positive_signal_category =
  case
    when feedback_type <> 'good' then null
    when lower(coalesce(title, '') || ' ' || coalesce(note, '')) ~
      '(ai agent|ai agents|agentic|llm agent|\mrag\M)'
      then 'strong_ai_agent_match'
    when lower(coalesce(title, '') || ' ' || coalesce(note, '')) ~
      '(workflow|automation|internal tools|operations automation)'
      then 'strong_workflow_automation_match'
    when lower(coalesce(title, '') || ' ' || coalesce(note, '')) ~
      '(\mgtm\M|go-to-market|sales enablement|\mrevops\M)'
      then 'strong_gtm_ai_match'
    when lower(coalesce(title, '') || ' ' || coalesce(note, '')) ~
      '(remote us|us remote|new york|san francisco|bay area)'
      then 'strong_location_match'
    else 'strong_role_match'
  end;

-- If a post has explicit not-good feedback, remove any positive feedback for
-- that same post. Not-good notes are the more specific human correction.
delete from public.role_feedback good_rows
using public.role_feedback bad_rows
where good_rows.post_id = bad_rows.post_id
  and good_rows.feedback_type = 'good'
  and bad_rows.feedback_type = 'not_good';

-- Remove duplicate rows of the same feedback type for the same post. Keep the
-- first row so old links and export ordering remain stable.
with ranked as (
  select
    id,
    row_number() over (
      partition by post_id, feedback_type
      order by created_at asc, id asc
    ) as rn
  from public.role_feedback
)
delete from public.role_feedback rf
using ranked
where rf.id = ranked.id
  and ranked.rn > 1;

-- Prevent the same accidental duplication pattern from coming back.
create unique index if not exists role_feedback_one_good_per_post_idx
  on public.role_feedback (post_id)
  where feedback_type = 'good';

create unique index if not exists role_feedback_one_not_good_per_post_idx
  on public.role_feedback (post_id)
  where feedback_type = 'not_good';

alter table public.role_feedback
  drop constraint if exists role_feedback_feedback_category_check;

alter table public.role_feedback
  add constraint role_feedback_feedback_category_check
  check (
    feedback_category in (
      'too_senior',
      'wrong_location',
      'not_hiring_post',
      'expired_post',
      'not_relevant_domain',
      'duplicate'
    )
  );

commit;
