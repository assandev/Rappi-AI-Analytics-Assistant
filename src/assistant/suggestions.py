"""Deterministic proactive suggestions for follow-up analysis."""

from __future__ import annotations

from typing import Any


INTENT_SUGGESTIONS: dict[str, list[str]] = {
    "top_n_ranking": [
        "Compare these results by zone type (Wealthy vs Non Wealthy)",
        "Check how these top zones have evolved over the last weeks",
        "Identify if these zones also perform well in Perfect Orders",
    ],
    "aggregation": [
        "Break this metric down by zone for more granularity",
        "Analyze how this metric has evolved over time",
        "Compare results across zone types or prioritization levels",
    ],
    "trend_analysis": [
        "Compare this trend across multiple zones",
        "Identify zones with declining trends in this metric",
        "Check if similar patterns exist in related metrics",
    ],
    "group_comparison": [
        "Analyze how this comparison evolves over time",
        "Break down results by country or city",
        "Check if similar gaps exist in other metrics",
    ],
    "multivariable_filter": [
        "Analyze trends for these zones over time",
        "Compare these zones against high-performing zones",
        "Identify potential drivers behind these patterns",
    ],
    "growth_analysis": [
        "Check if growth is sustainable over a longer time window",
        "Analyze quality metrics (Perfect Orders) for these zones",
        "Compare growth patterns across countries",
    ],
}

DEFAULT_SUGGESTIONS = [
    "Explore this metric across different dimensions",
    "Analyze trends over time",
    "Compare results across zones or segments",
]

EMPTY_RESULT_SUGGESTIONS = [
    "Remove one filter and re-run to widen the analysis scope",
    "Switch grouping to another dimension (country, city, or zone_type)",
    "Review this metric as a trend over the last weeks",
]


def _extract_intent(query: Any) -> str:
    """Extract normalized intent name from validated model or dict payload."""
    intent_value: Any = None
    if hasattr(query, "intent"):
        intent_value = getattr(query, "intent")
    elif isinstance(query, dict):
        intent_value = query.get("intent")

    if hasattr(intent_value, "value"):
        intent_value = intent_value.value

    if isinstance(intent_value, str):
        return intent_value.strip().lower()
    return ""


def _is_empty_result(result: dict[str, Any] | None) -> bool:
    """Return True when execution result indicates no matching rows."""
    if not isinstance(result, dict):
        return False
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and metadata.get("empty_result") is True:
        return True
    rows = result.get("rows")
    if isinstance(rows, list) and len(rows) == 0:
        return True
    return False


def generate_suggestions(query: Any, result: dict[str, Any] | None) -> list[str]:
    """Generate short intent-aware follow-up suggestions."""
    if _is_empty_result(result):
        return list(EMPTY_RESULT_SUGGESTIONS)

    intent = _extract_intent(query)
    suggestions = INTENT_SUGGESTIONS.get(intent, DEFAULT_SUGGESTIONS)
    return list(suggestions)

