"""Topic assignment from node IDs via word-frequency analysis or LLM."""

import hashlib
import json
import os
import re
import sys
from collections import Counter

STOP_WORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "has", "in", "is", "it", "its", "of", "on", "or", "that", "the",
    "to", "was", "with", "not", "no", "can", "may", "should", "must",
    "will", "do", "does", "did", "have", "had", "been", "being",
    "use", "used", "uses", "using",
})


def assign_topics(nodes, max_topics=20):
    """Group nodes by word-frequency topics extracted from node IDs.

    Returns dict of topic_name -> list of node_ids.
    """
    word_counts = Counter()
    node_words = {}

    for nid in nodes:
        words = set(nid.split("-")) - STOP_WORDS
        words = {w for w in words if len(w) > 2}
        node_words[nid] = words
        word_counts.update(words)

    top_words = [w for w, _ in word_counts.most_common(max_topics)]

    topics = {w: [] for w in top_words}
    assigned = set()

    for word in top_words:
        for nid in nodes:
            if nid in assigned:
                continue
            if word in node_words.get(nid, set()):
                topics[word].append(nid)
                assigned.add(nid)

    unassigned = [nid for nid in nodes if nid not in assigned]
    if unassigned:
        topics["other"] = unassigned

    return {k: v for k, v in topics.items() if v}


BATCH_PROMPT = """\
You are classifying beliefs from a Truth Maintenance System into semantic topics.

Assign each belief below to exactly one topic. Use descriptive, kebab-case \
topic names (e.g., "access-control", "error-handling", "belief-propagation"). \
Aim for 15-30 total topics. Each topic should group beliefs about the same \
conceptual area.

{known_topics_section}

## Beliefs

{belief_lines}

## Output

Return a JSON object mapping topic names to arrays of belief IDs:
{{"topic-name": ["belief-id-1", "belief-id-2"]}}

Return ONLY the JSON object. No explanation, no markdown fences, no other text."""

RECONCILE_PROMPT = """\
You are consolidating topic names from a belief classification task. \
Multiple batches independently assigned beliefs to topics. Some topics \
may be synonymous or near-duplicates.

## Current topics

{topic_lines}

## Rules

- Merge topics that cover the same concept (pick the more descriptive name)
- If a topic has fewer than 3 beliefs, merge it into the closest larger topic
- Target 15-30 final topics
- Every current topic name must appear as a key in your output

## Output

Return a JSON object mapping each current topic name to its canonical name:
{{"old-name": "canonical-name", "canonical-name": "canonical-name"}}

Return ONLY the JSON object. No explanation, no markdown fences, no other text."""


def assign_topics_llm(nodes, model, timeout=300, parallel=0, max_topics=25,
                      output_dir=None, no_cache=False):
    """Assign beliefs to LLM-determined semantic topics.

    Returns dict of topic_name -> list of node_ids.
    """
    from reasons.llm import invoke_model

    if not no_cache and output_dir:
        belief_hash = _compute_belief_hash(nodes)
        cached = _load_cached_topics(output_dir, belief_hash)
        if cached:
            print("Using cached LLM topic assignments", file=sys.stderr)
            return cached

    batches = _build_batches(nodes)
    all_topics = {}

    # Phase 1: batch 1 first to establish topic vocabulary
    print(f"Classifying {len(nodes)} beliefs into topics "
          f"({len(batches)} batches)...", file=sys.stderr)
    batch1_result = _classify_batch_safe(
        batches[0], [], nodes, model, timeout)
    _merge_into(all_topics, batch1_result)
    known_topics = sorted(all_topics.keys())
    print(f"  Batch 1/{len(batches)}: {len(batch1_result)} topics",
          file=sys.stderr)

    # Remaining batches (optionally parallel)
    remaining = batches[1:]
    if remaining:
        if parallel > 0:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = {
                    executor.submit(
                        _classify_batch_safe, batch, known_topics,
                        nodes, model, timeout
                    ): i
                    for i, batch in enumerate(remaining, 2)
                }
                for future in as_completed(futures):
                    batch_num = futures[future]
                    result = future.result()
                    _merge_into(all_topics, result)
                    print(f"  Batch {batch_num}/{len(batches)}: "
                          f"{len(result)} topics", file=sys.stderr)
        else:
            for i, batch in enumerate(remaining, 2):
                result = _classify_batch_safe(
                    batch, known_topics, nodes, model, timeout)
                _merge_into(all_topics, result)
                known_topics = sorted(all_topics.keys())
                print(f"  Batch {i}/{len(batches)}: {len(result)} topics",
                      file=sys.stderr)

    # Phase 2: reconciliation
    if len(all_topics) > max_topics + 5:
        print(f"  Reconciling {len(all_topics)} topics...", file=sys.stderr)
        all_topics = _reconcile_topics(all_topics, model, timeout)
        print(f"  Reconciled to {len(all_topics)} topics", file=sys.stderr)

    # Phase 3: validation
    all_topics = _validate_topics(all_topics, nodes)
    print(f"  Final: {len(all_topics)} topics", file=sys.stderr)

    if output_dir:
        belief_hash = _compute_belief_hash(nodes)
        _save_cached_topics(output_dir, belief_hash, all_topics)

    return all_topics


def _build_batches(nodes, batch_size=200):
    items = list(nodes.items())
    batches = []
    for i in range(0, len(items), batch_size):
        batch = []
        for nid, node in items[i:i + batch_size]:
            text = (node.get("text") or "")[:80]
            batch.append((nid, text))
        batches.append(batch)
    return batches


def _classify_batch(batch, known_topics, model, timeout):
    from reasons.llm import invoke_model

    belief_lines = "\n".join(
        f"- {nid}: {text}" for nid, text in batch)

    if known_topics:
        known_section = (
            "## Topics from prior batches (reuse these when appropriate)\n"
            + ", ".join(known_topics) + "\n"
            "You may also create new topics if none of these fit.\n"
        )
    else:
        known_section = ""

    prompt = BATCH_PROMPT.format(
        known_topics_section=known_section,
        belief_lines=belief_lines,
    )

    response = invoke_model(prompt, model=model, timeout=timeout)
    result = _parse_topic_json(response)

    # Validate: result should be {topic: [ids]}
    if not isinstance(result, dict):
        raise ValueError(f"Expected dict, got {type(result)}")

    valid_ids = {nid for nid, _ in batch}
    cleaned = {}
    for topic, ids in result.items():
        if not isinstance(ids, list):
            continue
        cleaned_ids = [i for i in ids if i in valid_ids]
        if cleaned_ids:
            cleaned[topic] = cleaned_ids

    return cleaned


def _classify_batch_safe(batch, known_topics, nodes, model, timeout):
    for attempt in range(2):
        try:
            return _classify_batch(batch, known_topics, model, timeout)
        except Exception as e:
            if attempt == 0:
                print(f"  WARN: batch failed, retrying: {e}", file=sys.stderr)
    print("  WARN: batch failed twice, using word-frequency fallback",
          file=sys.stderr)
    fallback_nodes = {nid: nodes.get(nid, {}) for nid, _ in batch}
    return assign_topics(fallback_nodes)


def _reconcile_topics(topics, model, timeout):
    from reasons.llm import invoke_model

    topic_lines = "\n".join(
        f"- {name} ({len(ids)} beliefs)"
        for name, ids in sorted(topics.items(), key=lambda x: -len(x[1]))
    )

    prompt = RECONCILE_PROMPT.format(topic_lines=topic_lines)
    response = invoke_model(prompt, model=model, timeout=timeout)

    try:
        mapping = _parse_topic_json(response)
    except Exception as e:
        print(f"  WARN: reconciliation failed, skipping: {e}",
              file=sys.stderr)
        return topics

    if not isinstance(mapping, dict):
        return topics

    merged = {}
    for old_name, ids in topics.items():
        canonical = mapping.get(old_name, old_name)
        if canonical in merged:
            merged[canonical].extend(ids)
        else:
            merged[canonical] = list(ids)

    return merged


def _validate_topics(topics, nodes):
    assigned = set()
    clean = {}
    for topic, ids in topics.items():
        deduped = [nid for nid in ids if nid not in assigned and nid in nodes]
        assigned.update(deduped)
        if deduped:
            clean[topic] = deduped

    missing = [nid for nid in nodes if nid not in assigned]
    if missing:
        clean["other"] = missing
        print(f"  WARN: {len(missing)} beliefs unassigned, added to 'other'",
              file=sys.stderr)

    return clean


def _parse_topic_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def _merge_into(target, source):
    for topic, ids in source.items():
        if topic in target:
            target[topic].extend(ids)
        else:
            target[topic] = list(ids)


def _compute_belief_hash(nodes):
    items = sorted((nid, (node.get("text") or "")) for nid, node in nodes.items())
    return hashlib.sha256(json.dumps(items).encode()).hexdigest()


def _load_cached_topics(output_dir, expected_hash):
    path = os.path.join(output_dir, ".topic_cache.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            cache = json.load(f)
        if cache.get("hash") == expected_hash:
            return cache["topics"]
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_cached_topics(output_dir, belief_hash, topics):
    path = os.path.join(output_dir, ".topic_cache.json")
    os.makedirs(output_dir, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"hash": belief_hash, "topics": topics}, f, indent=2)
