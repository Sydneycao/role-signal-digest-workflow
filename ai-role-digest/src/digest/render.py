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


def render(scored: list[ScoredPost]) -> str:
    top = sorted(scored, key=lambda s: s.score, reverse=True)[:MAX_RESULTS]
    return _tmpl.render(posts=top)
