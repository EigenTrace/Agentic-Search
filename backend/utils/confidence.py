"""Per-cell confidence scoring."""
from __future__ import annotations

import re

from models.schema import Confidence, SourceReference

_SPECIFIC_PATTERNS = [
    re.compile(r"\$\d"),                 # $ amount
    re.compile(r"\b\d{4}\b"),            # year
    re.compile(r"\b\d+(\.\d+)?\s?(%|m|b|million|billion|k)\b", re.IGNORECASE),
    re.compile(r"\b\d+(\.\d+)?\b"),      # any number
]
_VAGUE_TOKENS = {"various", "many", "several", "popular", "well-known", "unknown", "tbd", "n/a"}


def score_cell(
    value: str,
    sources: list[SourceReference],
    conflicts: list[str] | None,
    *,
    is_gap_fill: bool = False,
) -> Confidence:
    if not value or not value.strip():
        return Confidence.UNVERIFIED
    val = value.strip()

    if is_gap_fill and len(sources) <= 1:
        return Confidence.UNVERIFIED

    distinct_domains = {_domain(s.url) for s in sources if s.url}
    multi_source = len(distinct_domains) >= 2

    if multi_source and not conflicts:
        return Confidence.HIGH

    if conflicts:
        return Confidence.MEDIUM if multi_source else Confidence.LOW

    if _is_specific(val):
        return Confidence.MEDIUM
    return Confidence.LOW


def overall_confidence(cell_confidences: list[Confidence]) -> Confidence:
    if not cell_confidences:
        return Confidence.UNVERIFIED
    weights = {
        Confidence.HIGH: 3,
        Confidence.MEDIUM: 2,
        Confidence.LOW: 1,
        Confidence.UNVERIFIED: 0,
    }
    score = sum(weights[c] for c in cell_confidences) / len(cell_confidences)
    if score >= 2.3:
        return Confidence.HIGH
    if score >= 1.4:
        return Confidence.MEDIUM
    if score >= 0.6:
        return Confidence.LOW
    return Confidence.UNVERIFIED


def _is_specific(value: str) -> bool:
    low = value.lower().strip()
    if low in _VAGUE_TOKENS:
        return False
    for pat in _SPECIFIC_PATTERNS:
        if pat.search(value):
            return True
    if len(value) < 50 and any(w[:1].isupper() for w in value.split()):
        return True
    return False


def _domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001
        return url
