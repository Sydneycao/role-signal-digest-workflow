# Role Signal Digest Workflow

Automated role discovery, fit scoring, outreach drafting, and feedback tracking.

The project is designed to be reused for any job search. Change the search
queries, scoring rubric, and candidate background to target a different role,
industry, seniority level, location, or outreach style.

The daily workflow searches LinkedIn hiring posts, deduplicates already-seen
posts, scores fit with Claude, drafts outreach messages, and emails a digest
with feedback links.

## Workflow

```text
LinkedIn search via Apify
  -> Supabase seen-post dedupe
  -> Claude fit scoring
  -> Claude outreach drafting
  -> HTML email digest
  -> Good / Add feedback loop
```

The feedback loop is intentionally simple:

- `Good`: one click, saved as a positive signal.
- `Add feedback`: opens a small form where you explain why a result is not good.

Feedback is saved in Supabase table `role_feedback`.

## Repository Layout

```text
.github/workflows/daily-digest.yml       GitHub Actions scheduler
ai-role-digest/src/digest/               Python digest package
ai-role-digest/config/queries.yaml       LinkedIn search queries to customize
ai-role-digest/config/rubric.md          Fit scoring rubric to customize
ai-role-digest/supabase/schema.sql       Supabase tables
ai-role-digest/supabase/functions/       Supabase Edge Functions
docs/feedback.html                       Static feedback form for GitHub Pages
```

## Required Services

- Apify, for LinkedIn post search
- Anthropic, for fit scoring and message drafting
- Supabase, for dedupe and feedback storage
- SMTP email account, for sending the digest
- GitHub Actions, for scheduled runs
- GitHub Pages, for the feedback form page

## Environment Variables

GitHub Actions expects these repository secrets:

```text
APIFY_TOKEN
ANTHROPIC_API_KEY
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
SUPABASE_KEY
SMTP_HOST
SMTP_PORT
SMTP_USER
SMTP_PASS
EMAIL_TO
FEEDBACK_BASE_URL
FEEDBACK_FORM_URL
```

Optional runtime settings:

```text
CLAUDE_MODEL=claude-haiku-4-5
SCORE_THRESHOLD=7
MAX_RESULTS=20
SEND_ON_EMPTY=false
CANDIDATE_BACKGROUND=...
```

Example feedback URLs:

```text
FEEDBACK_BASE_URL=https://<project-ref>.supabase.co/functions/v1/role-feedback
FEEDBACK_FORM_URL=https://<github-username>.github.io/<repo-name>/feedback.html
```

## Customizing The Search

Update `ai-role-digest/config/queries.yaml` with the LinkedIn searches you want
to monitor.

Examples:

```yaml
queries:
  - '"product manager" "hiring" "remote"'
  - '"data analyst" "we are hiring"'
  - '"founding designer" startup'
```

Update `ai-role-digest/config/rubric.md` to define what a strong match means for
your search. This is where you describe target responsibilities, seniority,
industries, dealbreakers, and examples of roles to reject.

Update `CANDIDATE_BACKGROUND` if you want outreach drafts to reference a
specific candidate profile. If it is not set, the project uses the default
background in `ai-role-digest/src/digest/outreach.py`.

## Supabase Setup

Run the schema in `ai-role-digest/supabase/schema.sql`.

It creates:

- `seen_posts`: tracks LinkedIn posts that have already been processed.
- `role_feedback`: stores `good` clicks and `not_good` notes.

Deploy the feedback Edge Function:

```bash
cd /path/to/role-signal-digest-workflow/ai-role-digest
npx supabase@latest functions deploy role-feedback --project-ref <project-ref>
```

The function is configured in `ai-role-digest/supabase/config.toml` with
`verify_jwt = false` because feedback links are clicked from email.

If you want old `Add feedback` links to redirect to the static form, set this
Supabase function secret:

```bash
npx supabase@latest secrets set FEEDBACK_FORM_URL=https://<github-username>.github.io/<repo-name>/feedback.html --project-ref <project-ref>
```

## GitHub Pages Setup

The feedback form lives at `docs/feedback.html`.

Enable it in GitHub:

```text
Settings -> Pages -> Deploy from a branch -> master -> /docs
```

Then set GitHub secret `FEEDBACK_FORM_URL` to the published page URL.

## Running Locally

```bash
cd /path/to/role-signal-digest-workflow/ai-role-digest
cp .env.example .env
```

Fill in `.env`, then run:

```bash
python -m src.digest.main
```

Run tests with Python 3.11:

```bash
uv run --python 3.11 --with-requirements requirements.txt --with pytest pytest
```

Run lint:

```bash
ruff check .
```

## Feedback Review

Check recent feedback in Supabase SQL Editor:

```sql
select
  created_at,
  feedback_type,
  title,
  note,
  post_url
from public.role_feedback
order by created_at desc
limit 20;
```

Use the notes to tune:

- `ai-role-digest/config/rubric.md`
- `ai-role-digest/config/queries.yaml`
- outreach instructions in `ai-role-digest/src/digest/outreach.py`

## Success Metrics

Track the workflow as a funnel:

- Posts fetched
- New posts after dedupe
- Posts passing score threshold
- Good clicks
- Not-good feedback notes
- Outreach messages sent
- Replies received
- Calls booked

The north-star metric is useful conversations per week.

## Notes

Supabase Edge Functions are used as an API endpoint, not as the visible feedback
form host. Supabase rewrites browser `GET` HTML responses to plain text, so the
form is served from GitHub Pages and submits feedback to Supabase.
