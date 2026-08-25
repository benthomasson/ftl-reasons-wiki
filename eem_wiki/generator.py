"""Core generator: read network.json → render HTML files."""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from .templates import build_jinja_env, slugify
from .topics import assign_topics


def generate_site(input_path, output_dir, base_url="", project_name=None,
                   model=None, timeout=300, parallel=0, no_topic_cache=False,
                   topics_only=False, directory_root=None, summaries_dir=None,
                   topics_json=None):
    """Generate the full static site from a network.json export.

    Args:
        model: If set, use this LLM to generate summaries for topic and belief pages.
        timeout: LLM timeout in seconds.
        parallel: Number of concurrent LLM workers (0 = sequential).

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
    if topics_json:
        import sys
        with open(topics_json) as f:
            topics = json.load(f)
        assigned = {nid for ids in topics.values() for nid in ids}
        missing = [nid for nid in nodes if nid not in assigned]
        if missing:
            other_key = next((k for k in topics if k.lower() == "other"), "Other")
            topics.setdefault(other_key, []).extend(missing)
            print(f"  {len(missing)} beliefs unassigned, added to '{other_key}'",
                  file=sys.stderr)
        print(f"Using topics from {topics_json} ({len(topics)} topics)",
              file=sys.stderr)
    elif model:
        from .topics import assign_topics_llm
        topics = assign_topics_llm(
            nodes, model, timeout=timeout, parallel=parallel,
            output_dir=output_dir, no_cache=no_topic_cache)
    else:
        topics = assign_topics(nodes)
    node_topic = _build_node_topic_map(topics)
    depth_map = _compute_depths(nodes)

    saved_topic_sums, saved_belief_sums, saved_project_sum = _load_summaries(
        summaries_dir)
    topic_summaries = {}
    belief_summaries = {}
    project_summary = ""
    if model:
        if not topics_only:
            topic_summaries = _generate_topic_summaries(
                topics, nodes, model, timeout, parallel, saved_topic_sums)
            belief_summaries = _generate_belief_summaries(
                nodes, model, timeout, parallel, saved_belief_sums)
        elif topics_only == "with-summaries":
            topic_summaries = _generate_topic_summaries(
                topics, nodes, model, timeout, parallel, saved_topic_sums)
        project_summary = _generate_project_summary(
            meta.get("project_name", "Belief Wiki"), nodes, topics,
            model, timeout, saved_project_sum)
    elif summaries_dir:
        topic_summaries = saved_topic_sums
        belief_summaries = saved_belief_sums
        project_summary = saved_project_sum
    if summaries_dir:
        _save_summaries(summaries_dir, saved_topic_sums, saved_belief_sums,
                        project_summary)

    env = build_jinja_env()
    env.globals["directory_root"] = directory_root or ""

    os.makedirs(output_dir, exist_ok=True)

    _render_index(env, output_dir, meta, nodes, topics, project_summary)
    _render_topic_pages(env, output_dir, nodes, topics, topic_summaries)
    _render_belief_pages(env, output_dir, nodes, dependents, node_topic,
                         depth_map, meta, belief_summaries)
    _render_glossary(env, output_dir)
    _render_sitemap(output_dir, nodes, topics, base_url)
    _render_robots_txt(output_dir, base_url)
    _render_llms_txt(output_dir, meta, nodes, topics, directory_root)

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


def _load_summaries(summaries_dir):
    """Load topic, belief, and project summaries from named files."""
    if not summaries_dir:
        return {}, {}, ""
    topic_path = os.path.join(summaries_dir, "topic-summaries.json")
    belief_path = os.path.join(summaries_dir, "belief-summaries.json")
    project_path = os.path.join(summaries_dir, "project-summary.txt")
    topic_sums = {}
    belief_sums = {}
    project_sum = ""
    if os.path.exists(topic_path):
        try:
            with open(topic_path) as f:
                topic_sums = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    if os.path.exists(belief_path):
        try:
            with open(belief_path) as f:
                belief_sums = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    if os.path.exists(project_path):
        try:
            with open(project_path) as f:
                project_sum = f.read().strip()
        except OSError:
            pass
    return topic_sums, belief_sums, project_sum


def _save_summaries(summaries_dir, topic_sums, belief_sums, project_sum=""):
    """Write topic, belief, and project summaries for clean diffs."""
    if not summaries_dir:
        return
    os.makedirs(summaries_dir, exist_ok=True)
    if topic_sums:
        with open(os.path.join(summaries_dir, "topic-summaries.json"), "w") as f:
            json.dump(topic_sums, f, indent=2, sort_keys=True,
                      ensure_ascii=False)
            f.write("\n")
    if belief_sums:
        with open(os.path.join(summaries_dir, "belief-summaries.json"), "w") as f:
            json.dump(belief_sums, f, indent=2, sort_keys=True,
                      ensure_ascii=False)
            f.write("\n")
    if project_sum:
        with open(os.path.join(summaries_dir, "project-summary.txt"), "w") as f:
            f.write(project_sum + "\n")


def _generate_project_summary(project_name, nodes, topics, model, timeout,
                              saved):
    if saved:
        import sys
        print("Project summary: loaded from cache", file=sys.stderr)
        return saved

    import sys
    from .summarize import summarize_project
    print("Generating project summary...", file=sys.stderr)
    return summarize_project(project_name, nodes, topics, model, timeout)


def _generate_topic_summaries(topics, nodes, model, timeout, parallel,
                              saved):
    import sys
    from .summarize import summarize_topic

    summaries = {}
    needed = []
    for topic, nids in topics.items():
        if topic in saved:
            summaries[topic] = saved[topic]
        else:
            needed.append((topic, nids))

    loaded = len(topics) - len(needed)
    if loaded:
        print(f"Topic summaries: {loaded} loaded, {len(needed)} to generate",
              file=sys.stderr)
    if not needed:
        return summaries

    print(f"Generating {len(needed)} topic summaries...", file=sys.stderr)

    def _do_topic(topic, nids):
        beliefs = [
            {"id": nid, "text": nodes.get(nid, {}).get("text", ""),
             "truth_value": nodes.get(nid, {}).get("truth_value", "?")}
            for nid in nids
        ]
        result = summarize_topic(topic, beliefs, model, timeout)
        saved[topic] = result
        return result

    if parallel > 0:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(_do_topic, t, n): t
                for t, n in needed
            }
            for future in as_completed(futures):
                topic = futures[future]
                try:
                    summaries[topic] = future.result()
                    print(f"  Topic '{topic}' summarized", file=sys.stderr)
                except Exception as e:
                    print(f"  WARN: topic '{topic}' failed: {e}",
                          file=sys.stderr)
    else:
        for i, (topic, nids) in enumerate(needed, 1):
            print(f"  Summarizing topic {i}/{len(needed)}: {topic}...",
                  file=sys.stderr)
            try:
                summaries[topic] = _do_topic(topic, nids)
            except Exception as e:
                print(f"  WARN: topic '{topic}' failed: {e}",
                      file=sys.stderr)

    return summaries


def _generate_belief_summaries(nodes, model, timeout, parallel, saved):
    import sys
    from .summarize import summarize_belief

    summaries = {}
    needed = []
    for nid, node in nodes.items():
        if nid in saved:
            summaries[nid] = saved[nid]
        else:
            needed.append((nid, node))

    loaded = len(nodes) - len(needed)
    if loaded:
        print(f"Belief summaries: {loaded} loaded, {len(needed)} to generate",
              file=sys.stderr)
    if not needed:
        return summaries

    print(f"Generating {len(needed)} belief summaries...", file=sys.stderr)

    def _do_belief(nid, node):
        result = summarize_belief(nid, node, nodes, model, timeout)
        saved[nid] = result
        return result

    if parallel > 0:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=parallel) as executor:
            futures = {
                executor.submit(_do_belief, n, nd): n
                for n, nd in needed
            }
            done = 0
            for future in as_completed(futures):
                nid = futures[future]
                done += 1
                try:
                    summaries[nid] = future.result()
                    if done % 50 == 0:
                        print(f"  {done}/{len(needed)} beliefs summarized",
                              file=sys.stderr)
                except Exception as e:
                    print(f"  WARN: belief '{nid}' failed: {e}",
                          file=sys.stderr)
    else:
        for i, (nid, node) in enumerate(needed, 1):
            if i % 50 == 0:
                print(f"  Summarizing belief {i}/{len(needed)}...",
                      file=sys.stderr)
            try:
                summaries[nid] = _do_belief(nid, node)
            except Exception as e:
                print(f"  WARN: belief '{nid}' failed: {e}",
                      file=sys.stderr)

    return summaries


def _render_index(env, output_dir, meta, nodes, topics,
                  project_summary=""):
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
        project_summary=project_summary,
    )
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(html)


def _render_topic_pages(env, output_dir, nodes, topics, topic_summaries=None):
    tmpl = env.get_template("topic.html")
    summaries = topic_summaries or {}
    for topic, nids in topics.items():
        topic_dir = os.path.join(output_dir, "topic", slugify(topic))
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
            summary=summaries.get(topic, ""),
        )
        with open(os.path.join(topic_dir, "index.html"), "w") as f:
            f.write(html)


def _render_belief_pages(env, output_dir, nodes, dependents, node_topic,
                         depth_map, meta, belief_summaries=None):
    tmpl = env.get_template("belief.html")
    summaries = belief_summaries or {}

    for nid, node in nodes.items():
        belief_dir = os.path.join(output_dir, "belief", nid)
        os.makedirs(belief_dir, exist_ok=True)

        justifications = []
        for j in node.get("justifications", []):
            ant_details = [
                (aid, nodes.get(aid, {}).get("text", ""),
                 nodes.get(aid, {}).get("truth_value", "?"))
                for aid in j.get("antecedents", [])
            ]
            out_details = [
                (oid, nodes.get(oid, {}).get("text", ""),
                 nodes.get(oid, {}).get("truth_value", "?"))
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
            (did, nodes.get(did, {}).get("text", ""),
             nodes.get(did, {}).get("truth_value", "?"))
            for did in dep_ids
        ]

        retract_reason = node.get("metadata", {}).get("retract_reason", "")

        challenge_ids = node.get("metadata", {}).get("challenges", [])
        challenges = []
        for cid in challenge_ids:
            cnode = nodes.get(cid, {})
            defense = None
            for did, dnode in nodes.items():
                if dnode.get("metadata", {}).get("defense_target") == cid:
                    defense = did
                    break
            challenges.append({
                "id": cid,
                "text": cnode.get("text", ""),
                "truth_value": cnode.get("truth_value", "?"),
                "defense": defense,
            })

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
            challenges=challenges,
            dependents=dep_details,
            topic=topic,
            source=node.get("source", ""),
            source_url=node.get("source_url", ""),
            created_at=node.get("created_at", ""),
            reviewed_at=node.get("reviewed_at", ""),
            verified_at=node.get("verified_at", ""),
            summary=summaries.get(nid, ""),
            retract_reason=retract_reason,
        )
        with open(os.path.join(belief_dir, "index.html"), "w") as f:
            f.write(html)


def _render_glossary(env, output_dir):
    tmpl = env.get_template("glossary.html")
    glossary_dir = os.path.join(output_dir, "glossary")
    os.makedirs(glossary_dir, exist_ok=True)
    html = tmpl.render(
        title="Glossary",
        description="How to read this belief wiki — IN/OUT, premises, justifications, and more",
        canonical="",
        root="../",
        meta=None,
    )
    with open(os.path.join(glossary_dir, "index.html"), "w") as f:
        f.write(html)


def _render_sitemap(output_dir, nodes, topics, base_url):
    base = base_url.rstrip("/")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    lines.append(f'  <url><loc>{base}/</loc><priority>1.0</priority></url>')
    for topic in topics:
        lines.append(f'  <url><loc>{base}/topic/{slugify(topic)}/</loc>'
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


def _render_llms_txt(output_dir, meta, nodes, topics, directory_root=None):
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
    ]

    if directory_root:
        lines.extend([
            "## Other Wikis",
            "",
            f"This is one of several belief wikis. See {directory_root} for the full directory.",
            "",
        ])

    lines.extend([
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
    ])

    with open(os.path.join(output_dir, "llms.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")


def generate_directory_index(output_dir, wiki_stats):
    """Render a top-level directory page listing all wikis."""
    from .templates import build_jinja_env
    env = build_jinja_env()
    tmpl = env.get_template("directory.html")
    html = tmpl.render(
        title="EEM Belief Wikis",
        description="Directory of EEM belief network wikis",
        canonical="",
        root="",
        meta=None,
        wikis=wiki_stats,
    )
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "index.html"), "w") as f:
        f.write(html)
