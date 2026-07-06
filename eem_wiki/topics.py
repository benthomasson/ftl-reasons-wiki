"""Topic assignment from node IDs via word-frequency analysis."""

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
