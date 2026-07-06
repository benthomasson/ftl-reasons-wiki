"""Core generator: read network.json → render HTML files."""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from .templates import build_jinja_env
from .topics import assign_topics


def generate_site(input_path, output_dir, base_url="", project_name=None):
    """Generate the full static site from a network.json export.

    Returns dict with generation stats.
    """
    with open(input_path) as f:
        data = json.load(f)

    meta = data.get("meta", {})
    nodes = data.get("nodes", {})
    if project_name:
        meta["project_name"] = project_name
    elif not meta.get("project_name"):
        basename = os.path.basename(os.path.dirname(os.path.abspath(input_path)))
        meta["project_name"] = basename or "Belief Wiki"

    dependents = _build_dependents_index(nodes)
    topics = assign_topics(nodes)
    node_topic = _build_node_topic_map(topics)
    depth_map = _compute_depths(nodes)

    env = build_jinja_env()
    root = _relative_root("")

    os.makedirs(output_dir, exist_ok=True)

    _render_index(env, output_dir, meta, nodes, topics)
    _render_topic_pages(env, output_dir, nodes, topics)
    _render_belief_pages(env, output_dir, nodes, dependents, node_topic, depth_map, meta)
    _render_sitemap(output_dir, nodes, topics, base_url)
    _render_robots_txt(output_dir, base_url)
    _render_llms_txt(output_dir, meta, nodes, topics)

    in_count = sum(1 for n in nodes.values() if n.get("truth_value") == "IN")
    out_count = len(nodes) - in_count

    return {
        "beliefs": len(nodes),
        "topics": len(topics),
        "in_count": in_count,
        "out_count": out_count,
    }


def _build_dependents_index(nodes):
    """Invert the antecedent graph to get dependents for each node."""
    deps = defaultdict(set)
    for nid, node in nodes.items():
        for j in node.get("justifications", []):
            for ant in j.get("antecedents", []):
                deps[ant].add(nid)
            for out in j.get("outlist", []):
                deps[out].add(nid)
    return deps


def _build_node_topic_map(topics):
    """Map each node_id to its assigned topic."""
    mapping = {}
    for topic, nids in topics.items():
        for nid in nids:
            mapping[nid] = topic
    return mapping


def _compute_depths(nodes):
    """Compute derivation depth for each node (0 = premise)."""
    depths = {}

    def _depth(nid):
        if nid in depths:
            return depths[nid]
        node = nodes.get(nid)
        if not node or not node.get("justifications"):
            depths[nid] = 0
            return 0
        depths[nid] = -1  # cycle guard
        max_ant = 0
        for j in node["justifications"]:
            for ant in j.get("antecedents", []):
                d = _depth(ant)
                if d >= 0:
                    max_ant = max(max_ant, d + 1)
        depths[nid] = max_ant
        return max_ant

    for nid in nodes:
        _depth(nid)
    return depths


def _relative_root(from_path):
    """Compute relative root path from a page location."""
    return ""


def _render_index(env, output_dir, meta, nodes, topics):
    tmpl = env.get_template("index.html")
    in_count = len(nodes)
    out_count = sum(1 for n in nodes.values() if n.get("truth_value") == "OUT")
    html = tmpl.render(
        title=meta.get("project_name", "Belief Wiki"),
        description=f"EEM belief network with {len(nodes)} beliefs",
        canonical="",
        root="",
        meta=meta,
        project_name=meta.get("project_name", "Belief Wiki"),
        in_count=in_count,
        out_count=out_count,
        topics=topics,
    )
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(html)


def _render_topic_pages(env, output_dir, nodes, topics):
    tmpl = env.get_template("topic.html")
    for topic, nids in topics.items():
        topic_dir = os.path.join(output_dir, "topic", topic)
        os.makedirs(topic_dir, exist_ok=True)

        beliefs = []
        for nid in sorted(nids):
            node = nodes.get(nid, {})
            beliefs.append({
                "id": nid,
                "text": node.get("text", ""),
                "truth_value": node.get("truth_value", "?"),
            })

        html = tmpl.render(
            title=f"{topic} — Beliefs",
            description=f"Beliefs about {topic}",
            canonical="",
            root="../../",
            meta=None,
            topic_name=topic,
            beliefs=beliefs,
        )
        with open(os.path.join(topic_dir, "index.html"), "w") as f:
            f.write(html)


def _render_belief_pages(env, output_dir, nodes, dependents, node_topic, depth_map, meta):
    tmpl = env.get_template("belief.html")

    for nid, node in nodes.items():
        belief_dir = os.path.join(output_dir, "belief", nid)
        os.makedirs(belief_dir, exist_ok=True)

        justifications = []
        for j in node.get("justifications", []):
            ant_details = [
                (aid, nodes.get(aid, {}).get("text", ""))
                for aid in j.get("antecedents", [])
            ]
            out_details = [
                (oid, nodes.get(oid, {}).get("text", ""))
                for oid in j.get("outlist", [])
            ]
            justifications.append({
                "type": j.get("type", "SL"),
                "label": j.get("label", ""),
                "antecedents": j.get("antecedents", []),
                "outlist": j.get("outlist", []),
                "ant_details": ant_details,
                "out_details": out_details,
            })

        dep_ids = sorted(dependents.get(nid, set()))
        dep_details = [
            (did, nodes.get(did, {}).get("text", ""))
            for did in dep_ids
        ]

        is_premise = not node.get("justifications")
        topic = node_topic.get(nid, "other")
        text = node.get("text", "")

        html = tmpl.render(
            title=f"{nid}",
            description=text[:160] if text else "",
            canonical="",
            root="../../",
            meta=meta,
            node_id=nid,
            text=text,
            text_json=json.dumps(text),
            truth_value=node.get("truth_value", "?"),
            is_premise=is_premise,
            depth=depth_map.get(nid, 0),
            justifications=justifications,
            dependents=dep_details,
            topic=topic,
            source=node.get("source", ""),
            source_url=node.get("source_url", ""),
            created_at=node.get("created_at", ""),
            reviewed_at=node.get("reviewed_at", ""),
            verified_at=node.get("verified_at", ""),
        )
        with open(os.path.join(belief_dir, "index.html"), "w") as f:
            f.write(html)


def _render_sitemap(output_dir, nodes, topics, base_url):
    base = base_url.rstrip("/")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    lines.append(f'  <url><loc>{base}/</loc><priority>1.0</priority></url>')
    for topic in topics:
        lines.append(f'  <url><loc>{base}/topic/{xml_escape(topic)}/</loc>'
                      f'<priority>0.8</priority></url>')
    for nid in nodes:
        lines.append(f'  <url><loc>{base}/belief/{xml_escape(nid)}/</loc>'
                      f'<priority>0.5</priority></url>')
    lines.append('</urlset>')

    with open(os.path.join(output_dir, "sitemap.xml"), "w") as f:
        f.write("\n".join(lines))


def _render_robots_txt(output_dir, base_url):
    base = base_url.rstrip("/") if base_url else ""
    lines = [
        "User-agent: *",
        "Allow: /",
    ]
    if base:
        lines.append(f"Sitemap: {base}/sitemap.xml")
    with open(os.path.join(output_dir, "robots.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def _render_llms_txt(output_dir, meta, nodes, topics):
    name = meta.get("project_name", "Belief Network")
    in_count = sum(1 for n in nodes.values() if n.get("truth_value") == "IN")
    out_count = len(nodes) - in_count
    topic_list = ", ".join(sorted(topics.keys()))

    lines = [
        f"# {name}",
        "",
        f"This site contains {len(nodes)} beliefs ({in_count} IN, {out_count} OUT) "
        f"organized as a justified belief network.",
        "",
        "## Navigation",
        "",
        "- `/` — Index with topic list and statistics",
        "- `/topic/{name}/` — Beliefs grouped by topic",
        "- `/belief/{id}/` — Individual belief with justification chain, antecedents, and dependents",
        "",
        f"## Topics",
        "",
        topic_list,
        "",
        "## About",
        "",
        "Each belief is a justified claim with truth value (IN or OUT). Derived beliefs "
        "link to their antecedents — the beliefs they were reasoned from. Premises are "
        "direct observations with no antecedents. When a premise is retracted, all beliefs "
        "that depend on it are automatically retracted (truth maintenance).",
        "",
        "Built with ftl-reasons (https://github.com/benthomasson/ftl-reasons).",
    ]

    with open(os.path.join(output_dir, "llms.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
