# Role Signal Digest

A personal job-search digest that finds high-signal LinkedIn hiring posts and
emails the best matches to you—with a short fit explanation and a ready-to-edit
outreach message.

**The idea:** spend less time refreshing job boards and more time talking to the
right people.

The included setup is tuned for applied AI, automation, and AI transformation
roles. Fork it, change the searches, and make it yours.

> **No Anthropic API key or credit is required.** The default workflow uses
> local rule-based scoring and message templates.

## What You Get

Each digest includes:

- LinkedIn hiring posts that match your target roles
- A fit score and a concise explanation
- The original post and author profile links
- A personalized connection note and direct-message draft
- **Good** and **Add feedback** actions for improving future results

The workflow also remembers posts it has already processed, so the same result
does not keep appearing in your inbox.

## Quick Start

1. **Fork this repository** to your GitHub account.
2. **Connect four services:** Apify, Supabase, an email account, and GitHub
   Actions.
3. **Add your GitHub secrets** using the table below.
4. **Edit your searches** in
   [`ai-role-digest/config/queries.yaml`](ai-role-digest/config/queries.yaml).
5. **Run a dry test**, then enable the daily email.

The sections below walk through each step. You do not need to understand the
internal Python code to use the workflow.

## What You Need

| Service | What it does | Cost note |
| --- | --- | --- |
| [GitHub](https://github.com/) | Stores your fork and runs the daily workflow | GitHub Actions free allowance is usually enough for personal use |
| [Apify](https://apify.com/) | Searches public LinkedIn posts | Usage-based; the workflow includes conservative result limits |
| [Supabase](https://supabase.com/) | Remembers seen posts and stores feedback | The free tier is usually enough for personal use |
| An SMTP email account | Sends the digest | Gmail or another SMTP provider works |

Anthropic is optional and is not used by the default GitHub workflow.

## Setup

### 1. Fork the Repository

Click **Fork** at the top of this repository, then work from your own copy.

If you also want a local copy:

```bash
git clone https://github.com/<your-username>/role-signal-digest-workflow.git
cd role-signal-digest-workflow
```

### 2. Create the Supabase Project

1. Create a project in [Supabase](https://supabase.com/).
2. Open **SQL Editor** in the Supabase dashboard.
3. Copy and run
   [`ai-role-digest/supabase/schema.sql`](ai-role-digest/supabase/schema.sql).
4. From the `ai-role-digest` directory, deploy the feedback function:

```bash
npx supabase@latest login
npx supabase@latest functions deploy role-feedback --project-ref <project-ref>
```

You can find the project URL and API keys under **Project Settings → API**.

### 3. Publish the Feedback Page

In your GitHub fork, go to:

```text
Settings → Pages → Deploy from a branch → master → /docs
```

GitHub will publish a URL similar to:

```text
https://<your-username>.github.io/role-signal-digest-workflow/feedback.html
```

Give the Supabase feedback function that URL:

```bash
npx supabase@latest secrets set \
  FEEDBACK_FORM_URL=https://<your-username>.github.io/role-signal-digest-workflow/feedback.html \
  --project-ref <project-ref>
```

### 4. Add GitHub Secrets

In your fork, open **Settings → Secrets and variables → Actions**, then add:

| Secret | Where to get it |
| --- | --- |
| `APIFY_TOKEN` | Apify → Settings → Integrations → API tokens |
| `SUPABASE_URL` | Supabase → Project Settings → API → Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Project Settings → API → service role key |
| `SUPABASE_KEY` | Supabase anon/public key; optional fallback |
| `SMTP_HOST` | For Gmail: `smtp.gmail.com` |
| `SMTP_PORT` | For Gmail: `587` |
| `SMTP_USER` | The email address that sends the digest |
| `SMTP_PASS` | Your SMTP password; for Gmail, use an App Password |
| `EMAIL_TO` | The address that should receive the digest |
| `FEEDBACK_BASE_URL` | `https://<project-ref>.supabase.co/functions/v1/role-feedback` |
| `FEEDBACK_FORM_URL` | The GitHub Pages URL created above |

For Gmail, turn on 2-Step Verification and create an
[App Password](https://support.google.com/accounts/answer/185833). Do not use
your normal Google password as `SMTP_PASS`.

### 5. Choose What to Search For

Edit [`ai-role-digest/config/queries.yaml`](ai-role-digest/config/queries.yaml):

```yaml
queries:
  - '"product manager" "we are hiring" remote'
  - '"data analyst" hiring fintech'
  - '"founding designer" startup'
```

Start with a few focused searches. Broad queries create more noise and use more
Apify results.

The default scoring rules are designed for applied AI and automation roles. If
you are targeting a different role family, update the target and rejection
terms in [`ai-role-digest/src/digest/score.py`](ai-role-digest/src/digest/score.py).

### 6. Send a Test Digest

1. Open the **Actions** tab in your fork.
2. Select **AI Role Digest**.
3. Click **Run workflow**.
4. Check `email_dry_run` for the first run. This fetches and evaluates results
   without sending an email.
5. Review the run log, then run it again with `email_dry_run` unchecked.

After setup, GitHub Actions runs the digest every day at **8:00 AM New York
time**, including daylight-saving time changes.

## Using Your Digest

Every result has two feedback choices:

- **Good** — confirms that the result is relevant.
- **Add feedback** — lets you explain why a result missed the mark.

Feedback is saved across runs. Repeated, consistent signals can be reviewed and
applied as new filters; a single click does not immediately rewrite the rules.

## Common Changes

| I want to… | Change this |
| --- | --- |
| Search for different roles | `ai-role-digest/config/queries.yaml` |
| Change what counts as a match | Target and rejection terms in `ai-role-digest/src/digest/score.py` |
| Change the outreach wording | Templates in `ai-role-digest/src/digest/outreach.py` |
| Change the delivery time | Schedule in `.github/workflows/daily-digest.yml` |
| Show more or fewer results | Limits in `.github/workflows/daily-digest.yml` or the runtime environment |

## How It Works

```text
Search LinkedIn hiring posts
  → remove posts already processed
  → score and filter the new results
  → draft outreach messages
  → send the email digest
  → collect feedback for future filtering
```

Searches rotate based on recent performance, while hard limits keep each run
small. With the current defaults, the workflow fetches at most 50 dataset items
per run. Actual Apify charges depend on the actor's current pricing, so review
your Apify usage dashboard after the first few runs.

## Run Locally (Optional)

GitHub Actions is the easiest way to use the project. For local development:

```bash
cd ai-role-digest
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m src.digest.main
```

Fill in the same service values in `.env`. You can leave
`ANTHROPIC_API_KEY` empty when using the default `rules` and `template` modes.

Run the test suite with:

```bash
uv run --python 3.11 --with-requirements requirements.txt --with pytest pytest
```

## Troubleshooting

### I did not receive an email

Open **Actions → AI Role Digest** and inspect the latest run.

- A successful run may send nothing when there are no unseen matches above the
  score threshold. This is the default behavior.
- A run with `email_dry_run` enabled intentionally does not send email.
- Check that GitHub Actions is enabled and all SMTP secrets are correct.
- Check your spam folder and your email provider's App Password settings.
- Check the Apify dashboard if the run reports a quota or billing limit.

### My digest is too broad or too narrow

Make the searches in `queries.yaml` more specific or less restrictive, then use
the feedback links consistently for several runs. For a completely different
role family, update the scoring terms as well as the search queries.

### I want to reprocess recent posts

Run the workflow manually and enter an ISO date such as `2026-07-10` in
`backfill_since`. Posts first seen on or after that date will be evaluated
again.

## Privacy

This is a bring-your-own-accounts workflow. Your GitHub fork uses your Apify,
Supabase, and email credentials; secrets stay in GitHub Actions or your local
`.env` file. Never commit real keys or passwords to the repository.
