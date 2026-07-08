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
    .dates { font-size: 0.85em; color: var(--pico-muted-color); margin-top: -0.5em; }
    nav { margin-bottom: 1em; }
    footer { margin-top: 2em; font-size: 0.85em; color: var(--pico-muted-color); }
  </style>
  {% block head %}{% endblock %}
</head>
<body>
  <main class="container">
    <nav>
      {% if directory_root %}<a href="{{ root }}{{ directory_root }}">All Wikis</a> &rsaquo; {% endif %}
      <a href="{{ root }}">Home</a>
      &middot; <a href="{{ root }}glossary/">Glossary</a>
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

{% if project_summary %}
<section class="summary">
{{ project_summary|paragraphs }}
</section>
{% endif %}

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

{% if summary %}
<section class="summary">
{{ summary|paragraphs }}
</section>
{% endif %}

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
  {% endif %}
  {% if source %} &mdash; {% if source_url %}<a href="{{ source_url }}">{{ source }}</a>{% else %}{{ source }}{% endif %}{% endif %}
  </p>

  {% if created_at or reviewed_at or verified_at %}
  <p class="dates">
    {% if created_at %}Created {{ created_at }}{% endif %}
    {% if reviewed_at %}{% if created_at %} · {% endif %}Reviewed {{ reviewed_at }}{% endif %}
    {% if verified_at %}{% if created_at or reviewed_at %} · {% endif %}Verified {{ verified_at }}{% endif %}
  </p>
  {% endif %}

  {% if retract_reason %}
  <p><strong>Reason OUT:</strong> {{ retract_reason }}</p>
  {% endif %}

  <blockquote>{{ text }}</blockquote>

  {% if summary %}
  <section class="summary">
  <h2>Summary</h2>
  {{ summary|paragraphs }}
  </section>
  {% endif %}

  {% if justifications %}
  <h2>Justifications</h2>
  {% for j in justifications %}
  <details open>
    <summary>{{ j.type }}{% if j.label %} &mdash; {{ j.label }}{% endif %}</summary>
    {% if j.antecedents %}
    <p><strong>Antecedents</strong> (all must be IN):</p>
    <ul>
    {% for ant_id, ant_text, ant_tv in j.ant_details %}
      <li><span class="tag {{ 'tag-in' if ant_tv == 'IN' else 'tag-out' }}">{{ ant_tv }}</span>
        <a href="{{ root }}belief/{{ ant_id }}/" class="belief-id">{{ ant_id }}</a>
        — {{ ant_text }}</li>
    {% endfor %}
    </ul>
    {% endif %}
    {% if j.outlist %}
    <p><strong>Unless</strong> (any of these IN defeats this justification):</p>
    <ul>
    {% for out_id, out_text, out_tv in j.out_details %}
      <li><span class="tag {{ 'tag-in' if out_tv == 'IN' else 'tag-out' }}">{{ out_tv }}</span>
        <a href="{{ root }}belief/{{ out_id }}/" class="belief-id">{{ out_id }}</a>
        — {{ out_text }}</li>
    {% endfor %}
    </ul>
    {% endif %}
  </details>
  {% endfor %}
  {% endif %}

  {% if challenges %}
  <h2>Challenges</h2>
  <p>{{ challenges|length }} challenge{{ 's' if challenges|length != 1 else '' }}
    ({{ challenges|selectattr('truth_value', 'eq', 'IN')|list|length }} active,
     {{ challenges|selectattr('truth_value', 'eq', 'OUT')|list|length }} defeated)</p>
  <ul>
  {% for c in challenges %}
    <li><span class="tag {{ 'tag-in' if c.truth_value == 'IN' else 'tag-out' }}">{{ c.truth_value }}</span>
      <a href="{{ root }}belief/{{ c.id }}/" class="belief-id">{{ c.id }}</a>
      — {{ c.text }}
      {% if c.defense %}
        &mdash; defeated by <a href="{{ root }}belief/{{ c.defense }}/" class="belief-id">{{ c.defense }}</a>
      {% endif %}
    </li>
  {% endfor %}
  </ul>
  {% endif %}

  {% if dependents %}
  <h2>Dependents</h2>
  <p>These beliefs depend on this one:</p>
  <ul>
  {% for dep_id, dep_text, dep_tv in dependents %}
    <li><span class="tag {{ 'tag-in' if dep_tv == 'IN' else 'tag-out' }}">{{ dep_tv }}</span>
      <a href="{{ root }}belief/{{ dep_id }}/" class="belief-id">{{ dep_id }}</a>
      — {{ dep_text }}</li>
  {% endfor %}
  </ul>
  {% endif %}
</article>
{% endblock %}
"""


GLOSSARY_TEMPLATE = """\
{% extends "base.html" %}
{% block nav %} &rsaquo; Glossary{% endblock %}
{% block content %}
<h1>Glossary</h1>

<p>This wiki is generated from a <strong>justified belief network</strong> managed by a
<a href="https://github.com/benthomasson/ftl-reasons">Truth Maintenance System</a> (TMS).
The following terms explain how to read belief pages.</p>

<h2 id="in-out">IN and OUT</h2>
<p>Every belief has a truth value: <span class="tag tag-in">IN</span> or
<span class="tag tag-out">OUT</span>.</p>
<ul>
  <li><strong>IN</strong> means the belief is currently justified — its supporting evidence
    holds and no active defeater contradicts it. IN does not mean "proven true in all possible
    worlds"; it means "supported by the current state of the network."</li>
  <li><strong>OUT</strong> means the belief is <em>not currently justified</em>. This is not
    the same as "false." A belief goes OUT when one of its antecedents is retracted, when a
    defeater becomes active, or when it is explicitly retracted with a reason. OUT beliefs are
    retained in the network — they are graves you can visit, not pages that vanish.</li>
</ul>

<h2 id="premise-derived">Premise vs. Derived</h2>
<ul>
  <li>A <strong>premise</strong> is a direct observation or assertion with no justification chain.
    It is IN by default and can only go OUT if explicitly retracted.</li>
  <li>A <strong>derived belief</strong> is supported by one or more justifications that reference
    other beliefs. Its truth value is computed automatically from the network.</li>
</ul>

<h2 id="depth">Depth</h2>
<p>Depth measures how far a derived belief is from its nearest premise. Depth 0 is a premise.
Depth 1 means the belief is derived directly from premises. Depth 3 means there are three
levels of reasoning between this belief and the premises it ultimately rests on. Higher depth
means longer justification chains — more reasoning steps, but also more points where the
chain could break.</p>

<h2 id="justifications">Justifications</h2>
<p>A justification is a rule that says: "this belief is IN <em>if</em> all its
<strong>antecedents</strong> are IN <em>and</em> none of its <strong>unless</strong> (outlist)
nodes are IN." This is called an SL (Support List) justification.</p>
<ul>
  <li><strong>Antecedents</strong> — beliefs that must all be IN for this justification to hold.
    If any antecedent goes OUT, the justified belief goes OUT too (unless another justification
    still supports it).</li>
  <li><strong>Unless (outlist)</strong> — beliefs that defeat this justification if they become IN.
    This is the non-monotonic reasoning mechanism: it allows the network to express "A is true
    unless B" — default reasoning that can be overridden by new evidence.</li>
</ul>
<p>A belief can have multiple justifications. It stays IN as long as <em>at least one</em>
justification is satisfied.</p>

<h2 id="challenges">Challenges and Defenses</h2>
<p>A <strong>challenge</strong> is a belief that contests another belief by adding itself to
the target's outlist. When a challenge is IN, it defeats the target's justification — the
target goes OUT. A <strong>defense</strong> counters a challenge by placing the challenge in
<em>its</em> outlist, creating a dialectical structure: if the defense holds, the challenge
goes OUT, and the original belief is restored.</p>

<h2 id="retraction">Retraction and Cascades</h2>
<p>When a belief is retracted, the system propagates the change: every belief that depended
on the retracted belief is re-evaluated. If a derived belief has no remaining valid
justification, it goes OUT too. This cascade continues through the network until all truth
values are consistent. Retracted beliefs show a <strong>Reason OUT</strong> explaining why
they were retracted.</p>

<h2 id="topics">Topics</h2>
<p>Beliefs are grouped into topics by an LLM classifier that reads each belief's text and
assigns it to a semantic category. Topics are not part of the TMS data model — they are a
navigational layer added by the wiki generator to make large networks browsable.</p>
{% endblock %}
"""


DIRECTORY_TEMPLATE = """\
{% extends "base.html" %}
{% block content %}
<h1>EEM Belief Wikis</h1>

<p>{{ wikis|length }} belief networks available.</p>

<table>
  <thead><tr><th>Wiki</th><th>Beliefs</th><th>IN</th><th>OUT</th><th>Topics</th></tr></thead>
  <tbody>
  {% for w in wikis %}
    <tr>
      <td><a href="{{ w.name }}/">{{ w.project_name or w.name }}</a></td>
      <td>{{ w.beliefs }}</td>
      <td>{{ w.in_count }}</td>
      <td>{{ w.out_count }}</td>
      <td>{{ w.topics }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
"""


def _paragraphs(text):
    """Convert plain text with blank-line separators into <p> tags."""
    if not text:
        return ""
    from markupsafe import Markup, escape
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    return Markup("\n".join(f"<p>{escape(p)}</p>" for p in paras))


def build_jinja_env():
    """Create a Jinja2 environment with all templates loaded."""
    env = Environment(loader=BaseLoader())
    env.globals["root"] = ""
    env.filters["paragraphs"] = _paragraphs
    templates = {
        "base.html": BASE_TEMPLATE,
        "index.html": INDEX_TEMPLATE,
        "topic.html": TOPIC_TEMPLATE,
        "belief.html": BELIEF_TEMPLATE,
        "glossary.html": GLOSSARY_TEMPLATE,
        "directory.html": DIRECTORY_TEMPLATE,
    }
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
