-- Repair not-good feedback notes such as "not in the U.S." that were
-- previously misclassified before SQL normalization handled uppercase U.S.

update public.role_feedback
set feedback_category = 'wrong_location'
where feedback_type = 'not_good'
  and replace(lower(coalesce(note, '')), 'u.s.', 'us') ~
    '(not in us|not in the us|not in ny|not in sf)';
