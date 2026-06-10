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
</div>
{% endfor %}
</body>
</html>
"""

_env = Environment(loader=BaseLoader())
_tmpl = _env.from_string(_TEMPLATE)


def render(scored: list[ScoredPost]) -> str:
    top = sorted(scored, key=lambda s: s.score, reverse=True)[:MAX_RESULTS]
    return _tmpl.render(posts=top)
