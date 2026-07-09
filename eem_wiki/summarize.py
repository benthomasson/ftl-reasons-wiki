"""LLM-powered topic page summaries."""

import sys

TOPIC_SUMMARY_PROMPT = """\
You are summarizing a group of beliefs from a Truth Maintenance System (TMS) \
knowledge base. These beliefs are grouped under the topic "{topic}".

Write a 2-4 paragraph summary that:
1. Explains what this topic covers and why it matters
2. Highlights the key claims and how they relate to each other
3. Notes any important distinctions (e.g., which beliefs are premises vs derived)
4. Mentions if any beliefs are OUT (retracted) and what that implies

Write in clear, direct prose. Do not list the beliefs — synthesize them into \
a coherent narrative. Reference specific belief IDs inline in parentheses \
where relevant, e.g. (belief-id-here).

Output plain text paragraphs only. Do not use markdown formatting — no headers, \
no bullet lists, no bold/italic. Separate paragraphs with blank lines.

## Beliefs in this topic

{beliefs}"""

BELIEF_SUMMARY_PROMPT = """\
You are writing a plain-language summary for a belief in a Truth Maintenance System.

The belief is a formal claim that may be dense or technical. Write 1-2 sentences \
that explain what this belief means in plain language. Focus on the "so what" — \
why does this matter? What does it imply for the system?

Do not repeat the belief text verbatim. Do not use the word "belief". Just explain it.

Output plain text only. No markdown formatting — no bold, italic, headers, or lists.

Belief ID: {node_id}
Status: {truth_value}
Type: {node_type}

Claim: {text}

{context}"""


PROJECT_SUMMARY_PROMPT = """\
You are writing an overview summary for a belief network wiki called "{project_name}".

This knowledge base contains {total_beliefs} beliefs ({in_count} IN, {out_count} OUT) \
organized into {topic_count} topics by a Truth Maintenance System (TMS).

Write a 3-5 paragraph summary that:
1. Explains what this knowledge base is about — what domain does it cover?
2. Highlights the major themes and what the network has discovered
3. Notes the scale and structure — how many topics, what kinds of beliefs (premises vs derived)
4. Mentions what OUT (retracted) beliefs tell us about how understanding has evolved
5. Gives a reader a sense of why this knowledge base is valuable

Write in clear, direct prose for someone encountering this wiki for the first time. \
Do not list every topic — synthesize the big picture.

Output plain text paragraphs only. Do not use markdown formatting — no headers, \
no bullet lists, no bold/italic. Separate paragraphs with blank lines.

## Topics and their sizes

{topic_list}

## Sample beliefs (for flavor)

{sample_beliefs}"""


DEFEATER_SUMMARY_PROMPT = """\
You are writing a plain-language summary for a defeat verdict in a Truth Maintenance \
System. This belief explains why another belief's justification is invalid.

Summarize what the verdict finds is wrong with the justification, not what the \
defeated belief claims. Do not reinterpret the verdict as a problem with the \
defeated belief itself.

Do not repeat the belief text verbatim. Do not use the word "belief". Just explain \
what the verdict says is wrong.

Output plain text only. No markdown formatting — no bold, italic, headers, or lists.

Belief ID: {node_id}
Status: {truth_value}
Defeated belief: {defeats_node}

Verdict: {text}

{context}"""


REVIEW_SUMMARY_PROMPT = """\
You are reviewing an LLM-generated summary of a belief from a Truth Maintenance System.

The belief text is the authoritative source. The summary should accurately represent \
what the belief says — not reinterpret, reverse, or shift its subject.

Common failure modes for meta-beliefs (beliefs about other beliefs):
- USE/MENTION COLLAPSE: The summary describes the thing the belief is about, rather \
than what the belief says about it
- REVERSAL: The summary reverses the finding (e.g. "X lacks traceability" becomes \
"the reasoning couldn't be traced")
- SUBJECT SHIFT: The summary changes what the belief is about

Belief ID: {node_id}
Belief text: {text}
Summary: {summary}

Respond with exactly one of:
- PASS: Summary accurately represents the belief
- DRIFT: Summary shifts meaning but doesn't reverse it
- REVERSED: Summary reverses or substantially misrepresents the finding

Then one sentence explaining your verdict."""


def review_belief_summary(node_id, node, summary, model, timeout):
    """Review an LLM-generated summary against the belief text.

    Returns: {"verdict": "PASS"|"DRIFT"|"REVERSED", "explanation": str}
    """
    from reasons.llm import invoke_model

    prompt = REVIEW_SUMMARY_PROMPT.format(
        node_id=node_id,
        text=node.get("text", ""),
        summary=summary,
    )

    try:
        result = invoke_model(prompt, model=model, timeout=timeout)
    except Exception as e:
        return {"verdict": "ERROR", "explanation": str(e)}

    result = result.strip()
    for verdict in ("PASS", "DRIFT", "REVERSED"):
        if result.upper().startswith(verdict):
            explanation = result[len(verdict):].strip().lstrip(":").strip()
            return {"verdict": verdict, "explanation": explanation}

    return {"verdict": "UNKNOWN", "explanation": result}


def summarize_defeater(node_id, node, nodes, model, timeout):
    """Generate an LLM summary for a defeater belief using a tighter prompt."""
    from reasons.llm import invoke_model

    metadata = node.get("metadata") or {}
    defeats_node = metadata.get("defeats_node", "unknown")

    defeated = nodes.get(defeats_node, {})
    context_lines = [f"Defeated belief text: {defeated.get('text', '')}"]

    for j in defeated.get("justifications", []):
        for ant_id in j.get("antecedents", []):
            ant = nodes.get(ant_id, {})
            context_lines.append(f"Antecedent [{ant_id}]: {ant.get('text', '')}")

    prompt = DEFEATER_SUMMARY_PROMPT.format(
        node_id=node_id,
        truth_value=node.get("truth_value", "?"),
        defeats_node=defeats_node,
        text=node.get("text", ""),
        context="\n".join(context_lines),
    )

    try:
        return invoke_model(prompt, model=model, timeout=timeout)
    except Exception as e:
        print(f"  WARN: defeater summary for '{node_id}' failed: {e}",
              file=sys.stderr)
        return ""


def summarize_project(project_name, nodes, topics, model, timeout):
    """Generate an LLM summary for the project index page."""
    from reasons.llm import invoke_model

    in_count = sum(1 for n in nodes.values() if n.get("truth_value") == "IN")
    out_count = len(nodes) - in_count

    topic_lines = []
    for topic, nids in sorted(topics.items(), key=lambda x: -len(x[1])):
        topic_lines.append(f"- {topic} ({len(nids)} beliefs)")

    samples = []
    import random
    rng = random.Random(42)
    all_ids = list(nodes.keys())
    for nid in rng.sample(all_ids, min(20, len(all_ids))):
        node = nodes[nid]
        tv = node.get("truth_value", "?")
        samples.append(f"- [{tv}] {nid}: {node.get('text', '')[:150]}")

    prompt = PROJECT_SUMMARY_PROMPT.format(
        project_name=project_name,
        total_beliefs=len(nodes),
        in_count=in_count,
        out_count=out_count,
        topic_count=len(topics),
        topic_list="\n".join(topic_lines),
        sample_beliefs="\n".join(samples),
    )

    try:
        return invoke_model(prompt, model=model, timeout=timeout)
    except Exception as e:
        import sys
        print(f"  WARN: project summary failed: {e}", file=sys.stderr)
        return ""


def summarize_topic(topic, beliefs, model, timeout):
    """Generate an LLM summary for a topic page.

    Args:
        topic: Topic name.
        beliefs: List of dicts with id, text, truth_value.
        model: Model name for invoke_model.
        timeout: LLM timeout in seconds.

    Returns: Summary text or empty string on failure.
    """
    from reasons.llm import invoke_model

    belief_lines = []
    for b in beliefs:
        status = b.get("truth_value", "?")
        belief_lines.append(f"- [{status}] {b['id']}: {b.get('text', '')}")

    prompt = TOPIC_SUMMARY_PROMPT.format(
        topic=topic,
        beliefs="\n".join(belief_lines),
    )

    try:
        return invoke_model(prompt, model=model, timeout=timeout)
    except Exception as e:
        print(f"  WARN: summary for topic '{topic}' failed: {e}",
              file=sys.stderr)
        return ""


def summarize_belief(node_id, node, nodes, model, timeout):
    """Generate an LLM summary for an individual belief page.

    Args:
        node_id: Belief ID.
        node: Node dict from network.json.
        nodes: All nodes dict (for antecedent context).
        model: Model name for invoke_model.
        timeout: LLM timeout in seconds.

    Returns: Summary text or empty string on failure.
    """
    from reasons.llm import invoke_model

    is_premise = not node.get("justifications")
    node_type = "premise (direct observation)" if is_premise else "derived belief"

    context_lines = []
    for j in node.get("justifications", []):
        for ant_id in j.get("antecedents", []):
            ant = nodes.get(ant_id, {})
            context_lines.append(f"Antecedent [{ant_id}]: {ant.get('text', '')}")

    context = "\n".join(context_lines) if context_lines else "No antecedents (premise)."

    prompt = BELIEF_SUMMARY_PROMPT.format(
        node_id=node_id,
        truth_value=node.get("truth_value", "?"),
        node_type=node_type,
        text=node.get("text", ""),
        context=context,
    )

    try:
        return invoke_model(prompt, model=model, timeout=timeout)
    except Exception as e:
        print(f"  WARN: summary for '{node_id}' failed: {e}",
              file=sys.stderr)
        return ""
