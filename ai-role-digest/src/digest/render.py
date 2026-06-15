import os
from urllib.parse import urlencode

from jinja2 import BaseLoader, Environment

from .models import ScoredPost

MAX_RESULTS = 20

_TEMPLATE = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Role Digest</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:680px;margin:32px auto;color:#222;padding:0 16px}
  h1{font-size:1.3rem;margin-bottom:4px}
  .meta{font-size:.8rem;color:#666;margin-bottom:24px}
  .card{border:1px solid #e0e0e0;border-radius:8px;padding:16px;margin-bottom:16px}
  .score{display:inline-block;background:#1a73e8;color:#fff;border-radius:4px;
         padding:2px 8px;font-size:.8rem;font-weight:600;margin-bottom:8px}
  .reason{font-size:.9rem;color:#444;margin:8px 0}
  .links a{font-size:.85rem;color:#1a73e8;text-decoration:none;margin-right:12px}
  .links a:hover{text-decoration:underline}
  .feedback{margin-top:14px}
  .feedback a{display:inline-block;border:1px solid #dadce0;border-radius:6px;
              padding:6px 10px;font-size:.82rem;color:#1a73e8;text-decoration:none;
              margin-right:8px}
  .feedback a:hover{background:#f8fafd}
  .draft{border-top:1px solid #eee;margin-top:14px;padding-top:14px}
  .draft h2{font-size:1rem;margin:0 0 10px}
  .draft h3{font-size:.8rem;letter-spacing:.02em;text-transform:uppercase;
            color:#666;margin:12px 0 6px}
  .message{background:#f8f9fa;border:1px solid #eceff3;border-radius:6px;
           padding:10px 12px;font-size:.9rem;line-height:1.45;white-space:pre-wrap}
  .count{font-size:.75rem;color:#777;margin:4px 0 0}
</style>
</head>
<body>
<h1>AI Role Digest</h1>
<p class="meta">{{ posts|length }} new post{{ 's' if posts|length != 1 }} · sorted by fit score</p>
{% for s in posts %}
<div class="card">
  <span class="score">{{ s.score }}/10</span>
  <p class="reason">{{ s.reason }}</p>
  <div class="links">
    <a href="{{ s.post.url }}" target="_blank">View post</a>
    <a href="{{ s.poster_url }}" target="_blank">Reach out → {{ s.poster_name }}</a>
  </div>
  {% if s.feedback %}
  <div class="feedback">
    <a href="{{ s.feedback.good }}" target="_blank">Good</a>
    <a href="{{ s.feedback.add_feedback }}" target="_blank">Add feedback</a>
  </div>
  {% endif %}
  {% if s.outreach %}
  <div class="draft">
    <h2>{{ s.outreach.title }}</h2>
    <h3>Connection request</h3>
    <div class="message">{{ s.outreach.connection_request }}</div>
    <p class="count">{{ s.outreach.connection_request|length }}/200 characters</p>
    <h3>Direct message</h3>
    <div class="message">{{ s.outreach.direct_message }}</div>
    <p class="count">{{ s.outreach.direct_message|length }}/8,000 characters</p>
  </div>
  {% endif %}
</div>
{% endfor %}
</body>
</html>
"""

_env = Environment(loader=BaseLoader(), autoescape=True)
_tmpl = _env.from_string(_TEMPLATE)


def _feedback_links(
    scored: ScoredPost, api_url: str, form_url: str
) -> dict[str, str] | None:
    if not api_url:
        return None

    title = scored.outreach.title if scored.outreach else f"LinkedIn post by {scored.poster_name}"
    common = {
        "post_id": scored.post.id,
        "post_url": scored.post.url,
        "title": title,
    }
    form_params = {**common, "api_url": api_url}
    return {
        "good": f"{api_url}?{urlencode({**common, 'action': 'good'})}",
        "add_feedback": (
            f"{form_url}?{urlencode(form_params)}"
            if form_url
            else f"{api_url}?{urlencode({**common, 'action': 'add_feedback'})}"
        ),
    }


def _feedback_base_url() -> str:
    return os.environ.get("FEEDBACK_BASE_URL", "").strip()


def _feedback_form_url() -> str:
    return os.environ.get("FEEDBACK_FORM_URL", "").strip()


def render(scored: list[ScoredPost]) -> str:
    top = sorted(scored, key=lambda s: s.score, reverse=True)[:MAX_RESULTS]
    feedback_base_url = _feedback_base_url()
    feedback_form_url = _feedback_form_url()
    posts = [
        {
            "post": item.post,
            "score": item.score,
            "reason": item.reason,
            "poster_name": item.poster_name,
            "poster_url": item.poster_url,
            "outreach": item.outreach,
            "feedback": _feedback_links(item, feedback_base_url, feedback_form_url),
        }
        for item in top
    ]
    return _tmpl.render(posts=posts)
