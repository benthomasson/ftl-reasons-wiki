"""Jinja2 HTML templates for the static wiki."""

from jinja2 import Environment, BaseLoader

BASE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ title }}</title>
  {% if description %}<meta name="description" content="{{ description }}">{% endif %}
  {% if canonical %}<link rel="canonical" href="{{ canonical }}">{% endif %}
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
  <style>
    :root { --pico-font-size: 16px; }
    .tag { display: inline-block; padding: 0.1em 0.5em; border-radius: 4px;
           font-size: 0.85em; font-weight: 600; }
    .tag-in { background: #d4edda; color: #155724; }
    .tag-out { background: #f8d7da; color: #721c24; }
    .belief-list { list-style: none; padding: 0; }
    .belief-list li { padding: 0.5em 0; border-bottom: 1px solid var(--pico-muted-border-color); }
    .belief-list li:last-child { border-bottom: none; }
    .belief-id { font-family: var(--pico-font-family-monospace); font-size: 0.9em; }
    .meta-table { font-size: 0.9em; }
    .meta-table td:first-child { font-weight: 600; white-space: nowrap; padding-right: 1em; }
    nav { margin-bottom: 1em; }
    footer { margin-top: 2em; font-size: 0.85em; color: var(--pico-muted-color); }
  </style>
  {% block head %}{% endblock %}
</head>
<body>
  <main class="container">
    <nav>
      <a href="{{ root }}">Home</a>
      {% block nav %}{% endblock %}
    </nav>
    {% block content %}{% endblock %}
    <footer>
      <p>Generated from <a href="https://github.com/benthomasson/ftl-reasons">ftl-reasons</a> belief network
      {% if meta and meta.generator %} ({{ meta.generator }}){% endif %}</p>
    </footer>
  </main>
</body>
</html>
"""

INDEX_TEMPLATE = """\
{% extends "base.html" %}
{% block content %}
<h1>{{ project_name or "Belief Wiki" }}</h1>

<p>{{ in_count }} beliefs ({{ in_count - out_count }} IN, {{ out_count }} OUT)</p>

<h2>Topics</h2>
<table>
  <thead><tr><th>Topic</th><th>Beliefs</th></tr></thead>
  <tbody>
  {% for topic, nids in topics|items %}
    <tr>
      <td><a href="{{ root }}topic/{{ topic }}/">{{ topic }}</a></td>
      <td>{{ nids|length }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
"""

TOPIC_TEMPLATE = """\
{% extends "base.html" %}
{% block nav %} &rsaquo; <a href="{{ root }}">Topics</a>{% endblock %}
{% block content %}
<h1>{{ topic_name }}</h1>

<p>{{ beliefs|length }} beliefs
  ({{ beliefs|selectattr('truth_value', 'eq', 'IN')|list|length }} IN,
   {{ beliefs|selectattr('truth_value', 'eq', 'OUT')|list|length }} OUT)</p>

<ul class="belief-list">
{% for b in beliefs %}
  <li>
    <span class="tag {{ 'tag-in' if b.truth_value == 'IN' else 'tag-out' }}">{{ b.truth_value }}</span>
    <a href="{{ root }}belief/{{ b.id }}/" class="belief-id">{{ b.id }}</a>
    <br>{{ b.text }}
  </li>
{% endfor %}
</ul>
{% endblock %}
"""

BELIEF_TEMPLATE = """\
{% extends "base.html" %}
{% block head %}
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Claim",
  "name": "{{ node_id }}",
  "text": {{ text_json }},
  "truthValue": "{{ truth_value }}"
  {% if source_url %}, "citation": "{{ source_url }}"{% endif %}
}
</script>
{% endblock %}
{% block nav %} &rsaquo; <a href="{{ root }}topic/{{ topic }}/">{{ topic }}</a>{% endblock %}
{% block content %}
<article>
  <h1>{{ node_id }}</h1>

  <p><span class="tag {{ 'tag-in' if truth_value == 'IN' else 'tag-out' }}">{{ truth_value }}</span>
  {% if is_premise %} <span class="tag">premise</span>
  {% else %} <span class="tag">derived{% if depth %} (depth {{ depth }}){% endif %}</span>
  {% endif %}</p>

  <blockquote>{{ text }}</blockquote>

  {% if justifications %}
  <h2>Justifications</h2>
  {% for j in justifications %}
  <details open>
    <summary>{{ j.type }}{% if j.label %} &mdash; {{ j.label }}{% endif %}</summary>
    {% if j.antecedents %}
    <p><strong>Antecedents</strong> (all must be IN):</p>
    <ul>
    {% for ant_id, ant_text in j.ant_details %}
      <li><a href="{{ root }}belief/{{ ant_id }}/" class="belief-id">{{ ant_id }}</a>
        — {{ ant_text }}</li>
    {% endfor %}
    </ul>
    {% endif %}
    {% if j.outlist %}
    <p><strong>Unless</strong> (any of these IN defeats this justification):</p>
    <ul>
    {% for out_id, out_text in j.out_details %}
      <li><a href="{{ root }}belief/{{ out_id }}/" class="belief-id">{{ out_id }}</a>
        — {{ out_text }}</li>
    {% endfor %}
    </ul>
    {% endif %}
  </details>
  {% endfor %}
  {% endif %}

  {% if dependents %}
  <h2>Dependents</h2>
  <p>These beliefs depend on this one:</p>
  <ul>
  {% for dep_id, dep_text in dependents %}
    <li><a href="{{ root }}belief/{{ dep_id }}/" class="belief-id">{{ dep_id }}</a>
      — {{ dep_text }}</li>
  {% endfor %}
  </ul>
  {% endif %}

  <h2>Details</h2>
  <table class="meta-table">
    {% if source %}<tr><td>Source</td><td>{% if source_url %}<a href="{{ source_url }}">{{ source }}</a>{% else %}{{ source }}{% endif %}</td></tr>{% endif %}
    {% if created_at %}<tr><td>Created</td><td>{{ created_at }}</td></tr>{% endif %}
    {% if reviewed_at %}<tr><td>Reviewed</td><td>{{ reviewed_at }}</td></tr>{% endif %}
    {% if verified_at %}<tr><td>Verified</td><td>{{ verified_at }}</td></tr>{% endif %}
  </table>
</article>
{% endblock %}
"""


def build_jinja_env():
    """Create a Jinja2 environment with all templates loaded."""
    env = Environment(loader=BaseLoader())
    env.globals["root"] = ""
    templates = {
        "base.html": BASE_TEMPLATE,
        "index.html": INDEX_TEMPLATE,
        "topic.html": TOPIC_TEMPLATE,
        "belief.html": BELIEF_TEMPLATE,
    }
    for name, source in templates.items():
        env.loader = _DictLoader(templates)
    return env


class _DictLoader(BaseLoader):
    def __init__(self, templates):
        self._templates = templates

    def get_source(self, environment, template):
        if template in self._templates:
            source = self._templates[template]
            return source, template, lambda: True
        raise Exception(f"Template {template!r} not found")
