"""Jinja2 HTML templates for the static wiki."""

import re

from jinja2 import Environment, BaseLoader


def slugify(text):
    """Convert topic name to URL-safe slug: lowercase, hyphens, no special chars."""
    text = text.lower().strip()
    text = re.sub(r'[&]+', 'and', text)
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

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
      <td><a href="{{ root }}topic/{{ topic|slugify }}/">{{ topic }}</a></td>
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
{% block nav %} &rsaquo; <a href="{{ root }}topic/{{ topic|slugify }}/">{{ topic }}</a>{% endblock %}
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

  {% if retract_reason and truth_value == 'OUT' %}
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
  {% if justifications|length > 1 %}
  <p>This belief has {{ justifications|length }} justifications &mdash; it is IN if <em>any one</em> holds.</p>
  {% endif %}
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
Every belief on this site is a justified claim with an inspectable &ldquo;why.&rdquo;
Beliefs that have been abandoned are graves you can visit, not pages that vanish &mdash;
the record of what was believed and why it was given up is itself knowledge.
The following terms explain how to read belief pages.</p>

<h2 id="premise-derived">Premise vs. Derived</h2>
<ul>
  <li>A <strong>premise</strong> is a direct observation or assertion with no justification chain.
    It is IN by default and can only go OUT if explicitly retracted.</li>
  <li>A <strong>derived belief</strong> is supported by one or more justifications that reference
    other beliefs (see <a href="#justifications">Justifications</a> below). Its truth value is
    computed automatically from the network.</li>
</ul>

<h2 id="in-out">IN and OUT</h2>
<p>Every belief has a truth value: <span class="tag tag-in">IN</span> or
<span class="tag tag-out">OUT</span>.</p>
<ul>
  <li><strong>IN</strong> means the belief is currently justified &mdash; its supporting evidence
    holds and no active defeater contradicts it. IN does not mean &ldquo;proven true in all possible
    worlds&rdquo;; it means &ldquo;supported by the current state of the network.&rdquo;</li>
  <li><strong>OUT</strong> means the belief is <em>not currently justified</em>. This is not
    the same as &ldquo;false.&rdquo; A belief goes OUT in two distinct ways:
    <ul>
      <li><strong>Explicit retraction</strong> &mdash; someone (a human or an agent) marks the belief
        OUT with a stated reason. These beliefs show a <strong>Reason OUT</strong> on their page.</li>
      <li><strong>Cascade</strong> &mdash; a belief the network depended on went OUT, and this
        belief lost its last valid justification as a result. Cascade-OUT beliefs have no
        Reason OUT label; the cause is visible in their justification chain (one or more
        antecedents will be OUT).</li>
    </ul>
    OUT beliefs are retained in the network rather than deleted. The record of what was
    believed and why it was given up is itself knowledge.</li>
</ul>

<h2 id="well-foundedness">Well-Foundedness</h2>
<p>IN status must ultimately be grounded in premises &mdash; no belief can hold itself up by
its own bootstraps. If two beliefs each list the other as an antecedent with no premise
anchor, neither can be IN. This well-foundedness constraint prevents circular support and
ensures that every IN belief traces back to at least one direct observation or assertion.</p>

<h2 id="depth">Depth</h2>
<p>Depth measures how far a derived belief is from the premises it rests on. Depth 0 is a
premise. Depth 1 means the belief is derived directly from premises. Depth 2 means it
depends on a depth-1 belief, and so on. When a belief has multiple justifications with
different chain lengths, depth reflects the <em>longest</em> chain (maximum over all
antecedents across all justifications). Higher depth means more reasoning steps between
this belief and the observations it ultimately depends on &mdash; more inferential distance,
but also more points where the chain could break.</p>

<h2 id="justifications">Justifications</h2>
<p>A justification is a rule that says: &ldquo;this belief is IN <em>if</em> all its
<strong>antecedents</strong> are IN <em>and</em> none of its <strong>unless</strong> (outlist)
nodes are IN.&rdquo; This is called an SL (Support List) justification &mdash; the term
comes from <a href="https://en.wikipedia.org/wiki/Reason_maintenance">Doyle&rsquo;s 1979
truth maintenance system</a>.</p>
<ul>
  <li><strong>Antecedents</strong> &mdash; beliefs that must all be IN for this justification to hold.
    If any antecedent goes OUT, the justified belief goes OUT too (unless another justification
    still supports it).</li>
  <li><strong>Unless (outlist)</strong> &mdash; beliefs that defeat this justification if they become IN.
    This is the non-monotonic reasoning mechanism: it allows the network to express &ldquo;A is true
    unless B&rdquo; &mdash; default reasoning that can be overridden by new evidence.</li>
</ul>
<p>A belief can have multiple justifications. It stays IN as long as <em>at least one</em>
justification is satisfied.</p>

<h2 id="challenges">Challenges and Defenses</h2>
<p>A <strong>challenge</strong> is a belief that contests another belief by adding itself to
the outlist of <em>every</em> justification the target has. This means a single challenge
defeats all of the target&rsquo;s justifications at once &mdash; the target goes OUT unless
a defense neutralizes the challenge. If the target is a premise (no justifications), it is
converted to a justified node with the challenge in its outlist.</p>
<p>A <strong>defense</strong> counters a challenge using the same mechanism in reverse: it
places the challenge in <em>its own</em> outlist, creating a dialectical structure. Since
the defense is IN by default, the challenge goes OUT, which removes it as a defeater and
restores the original belief. Because a defense is itself a belief, it can be challenged
in turn &mdash; the structure recurses arbitrarily, producing chains of challenge, defense,
counter-challenge, and so on.</p>

<h2 id="nogoods">Nogoods and Dependency-Directed Backtracking</h2>
<p>A <strong>nogood</strong> is a recorded contradiction &mdash; a set of beliefs that cannot
all be IN simultaneously. When the system detects a nogood, it performs
<strong>dependency-directed backtracking</strong>: it traces the contradiction to its root
causes and retracts the least-entrenched premise responsible. This is more targeted than
blind retraction &mdash; the system uses the justification graph to find the weakest link
rather than arbitrarily choosing what to give up. Beliefs retracted by backtracking carry
a Reason OUT explaining the contradiction that triggered the retraction.</p>

<h2 id="retraction">Retraction and Cascades</h2>
<p>When a belief is explicitly retracted, the system propagates the change: every derived
belief that depended on the retracted belief is re-evaluated. If a derived belief has no
remaining valid justification, it goes OUT too. This cascade continues through the network
until all truth values are consistent.</p>
<p>Only explicitly retracted beliefs show a <strong>Reason OUT</strong> on their wiki page.
Cascade-OUT beliefs have no Reason OUT &mdash; instead, you can trace the cause by following
their justification chain until you find the antecedent that went OUT.</p>

<h2 id="reading-a-belief-page">Reading a Belief Page</h2>
<p>Each belief page is laid out top to bottom: the status line
(<span class="tag tag-in">IN</span> or <span class="tag tag-out">OUT</span>,
premise or derived with depth, and source provenance), optional dates, the
<strong>Reason OUT</strong> if explicitly retracted, the canonical belief text as a
blockquote, a plain-language <strong>Summary</strong>, then the graph edges &mdash;
<strong>Justifications</strong> upward (antecedents and unless nodes, each with their own
truth value tags), optional <strong>Challenges</strong>, and
<strong>Dependents</strong> downward (beliefs that cite this one). Every linked belief is
clickable, so you can walk the justification graph in either direction.</p>

<h2 id="provenance">Provenance</h2>
<p>Belief pages show provenance metadata when available: the <strong>source</strong> (where
the belief was observed or derived from, such as a code exploration entry or review report),
an optional <strong>source URL</strong> for external references, and timestamps for when the
belief was <strong>created</strong>, last <strong>reviewed</strong>, and last
<strong>verified</strong>. Provenance appears inline on the status line and as dates below it.
For code-domain beliefs, the source file is the ground truth. For world-knowledge beliefs,
provenance becomes critical metadata for resolving contradictions.</p>

<h2 id="topics">Topics</h2>
<p>Beliefs are grouped into topics by an LLM classifier that reads each belief&rsquo;s text and
assigns it to a semantic category. Topics are not part of the TMS data model &mdash; they are a
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
    env.filters["slugify"] = slugify
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
