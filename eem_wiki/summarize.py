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
