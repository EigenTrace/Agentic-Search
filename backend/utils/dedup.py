"""Entity name normalisation and fuzzy clustering."""
from __future__ import annotations

import re
from typing import Iterable

from thefuzz import fuzz

_SUFFIX_PATTERN = re.compile(
    r"\b(inc\.?|llc\.?|ltd\.?|corp\.?|corporation|co\.?|company|gmbh|s\.a\.|s\.r\.l\.|plc|sa)\b",
    re.IGNORECASE,
)
_PUNCT_PATTERN = re.compile(r"[^\w\s]")


def normalize_name(name: str) -> str:
    n = (name or "").lower().strip()
    n = _SUFFIX_PATTERN.sub("", n)
    n = _PUNCT_PATTERN.sub(" ", n)
    n = " ".join(n.split())
    return n


def same_entity(a: str, b: str, threshold: int = 85) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        # Guard against tiny tokens — "ai" in "openai" should not match a brand "AI".
        if min(len(na), len(nb)) >= 4:
            return True
    return fuzz.token_sort_ratio(na, nb) >= threshold


def cluster_names(names: Iterable[str], threshold: int = 85) -> list[list[str]]:
    """Greedy cluster: each name joins the first cluster whose centroid matches."""
    clusters: list[list[str]] = []
    for name in names:
        placed = False
        for cluster in clusters:
            if same_entity(name, cluster[0], threshold=threshold):
                cluster.append(name)
                placed = True
                break
        if not placed:
            clusters.append([name])
    return clusters


def best_canonical(names: list[str]) -> str:
    """Pick the most informative name: prefer ones with proper-case + longest."""
    def score(n: str) -> tuple[int, int]:
        proper = sum(1 for w in n.split() if w[:1].isupper())
        return (proper, len(n))
    return sorted(names, key=score, reverse=True)[0]
