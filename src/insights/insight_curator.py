"""Deterministic curation layer for raw detector insights."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.insights.schemas import InsightCategory, InsightItem


CATEGORIES: list[InsightCategory] = [
    "anomalies",
    "trends",
    "benchmarking",
    "correlations",
    "opportunities",
]

CATEGORY_BONUS: dict[InsightCategory, float] = {
    "opportunities": 8.0,
    "trends": 7.0,
    "anomalies": 6.0,
    "benchmarking": 5.0,
    "correlations": 4.0,
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
        if result != result:  # NaN guard
            return default
        return result
    except (TypeError, ValueError):
        return default


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _zone_key(insight: dict[str, Any]) -> str:
    country = str(insight.get("country") or "").strip().lower()
    city = str(insight.get("city") or "").strip().lower()
    zone = str(insight.get("zone") or "").strip().lower()
    if zone:
        return f"{country}|{city}|{zone}"
    return ""


def _summary_signature(insight: dict[str, Any]) -> str:
    summary = _normalize_text(insight.get("summary"))
    if len(summary) > 120:
        summary = summary[:120]
    return summary


def _validate_minimum_fields(insight: dict[str, Any]) -> bool:
    category = insight.get("category")
    title = _normalize_text(insight.get("title"))
    metric = _normalize_text(insight.get("metric"))
    summary = _normalize_text(insight.get("summary"))
    evidence = insight.get("evidence")

    if category not in CATEGORIES:
        return False
    if not title or not metric or not summary:
        return False
    if not isinstance(evidence, dict):
        return False
    return True


def _is_noisy_anomaly(insight: dict[str, Any]) -> bool:
    if insight.get("category") != "anomalies":
        return False

    evidence = insight.get("evidence", {})
    baseline = abs(_to_float(evidence.get("week_1_value"), 0.0))
    current = _to_float(evidence.get("week_0_value"), 0.0)
    change_pct = abs(_to_float(evidence.get("pct_change"), 0.0))
    abs_change = abs(current - _to_float(evidence.get("week_1_value"), 0.0))

    if baseline < 0.05 and abs_change < 0.05:
        return True
    if change_pct > 5.0 and abs_change < 0.2:
        return True
    if abs_change < 0.01:
        return True
    return False


def filter_noisy_insights(raw_insights: list[dict]) -> list[dict]:
    """Filter low-quality or noisy insights using deterministic rules."""
    filtered: list[dict] = []
    for insight in raw_insights:
        if not isinstance(insight, dict):
            continue
        if not _validate_minimum_fields(insight):
            continue
        if _is_noisy_anomaly(insight):
            continue
        filtered.append(dict(insight))
    return filtered


def _score_insight(insight: dict[str, Any]) -> float:
    severity = _to_float(insight.get("severity_score"), 0.0)
    category = insight.get("category")
    category_bonus = CATEGORY_BONUS.get(category, 0.0) if category in CATEGORIES else 0.0

    evidence = insight.get("evidence", {})
    affected_scope = max(1.0, _to_float(evidence.get("affected_zones_count"), 1.0))
    breadth_bonus = min(12.0, affected_scope)

    actionability_bonus = 3.0 if _normalize_text(insight.get("recommendation_hint")) else 0.0
    score = severity * 0.75 + category_bonus + breadth_bonus + actionability_bonus
    return round(score, 2)


def _rerank(insights: list[dict]) -> list[dict]:
    ranked = [dict(item) for item in insights]
    for item in ranked:
        item["priority_score"] = _score_insight(item)
    ranked.sort(
        key=lambda item: (_to_float(item.get("priority_score")), _to_float(item.get("severity_score"))),
        reverse=True,
    )
    return ranked


def deduplicate_insights(insights: list[dict]) -> list[dict]:
    """Drop redundant findings by category/location/metric and repeated summary signatures."""
    ranked = _rerank(insights)
    by_primary_key: set[tuple[str, str, str]] = set()
    by_summary_signature: set[tuple[str, str, str]] = set()
    deduped: list[dict] = []

    for insight in ranked:
        category = str(insight.get("category"))
        zone_key = _zone_key(insight)
        metric = _normalize_text(insight.get("metric"))
        signature = _summary_signature(insight)

        primary_key = (category, zone_key, metric)
        summary_key = (category, zone_key, signature)

        if zone_key and primary_key in by_primary_key:
            continue
        if zone_key and summary_key in by_summary_signature:
            continue

        deduped.append(insight)
        if zone_key:
            by_primary_key.add(primary_key)
            by_summary_signature.add(summary_key)

    return deduped


def limit_repeated_zones(insights: list[dict], max_per_zone: int = 1) -> list[dict]:
    """Limit how many insights from the same zone can appear in executive candidates."""
    if max_per_zone < 1:
        max_per_zone = 1

    ranked = _rerank(insights)
    counts: dict[str, int] = defaultdict(int)
    limited: list[dict] = []

    for insight in ranked:
        zone_key = _zone_key(insight)
        if not zone_key:
            limited.append(insight)
            continue
        if counts[zone_key] >= max_per_zone:
            continue
        counts[zone_key] += 1
        limited.append(insight)

    return limited


def apply_category_diversity(
    insights: list[dict],
    max_summary: int = 5,
    max_per_category: int = 2,
) -> list[dict]:
    """Build a diverse executive summary selection."""
    if max_summary <= 0:
        return []

    ranked = _rerank(insights)
    category_buckets: dict[str, list[dict]] = {category: [] for category in CATEGORIES}
    for insight in ranked:
        category = str(insight.get("category"))
        if category in category_buckets:
            category_buckets[category].append(insight)

    selected: list[dict] = []
    category_counts: dict[str, int] = defaultdict(int)
    selected_ids: set[int] = set()

    for category in CATEGORIES:
        if len(selected) >= max_summary:
            break
        if category_buckets[category]:
            candidate = category_buckets[category][0]
            selected.append(candidate)
            selected_ids.add(id(candidate))
            category_counts[category] += 1

    for insight in ranked:
        if len(selected) >= max_summary:
            break
        if id(insight) in selected_ids:
            continue
        category = str(insight.get("category"))
        if category_counts[category] >= max_per_category:
            continue
        selected.append(insight)
        selected_ids.add(id(insight))
        category_counts[category] += 1

    return selected


def group_insights_by_category(insights: list[dict], max_per_category: int = 3) -> dict[str, list[dict]]:
    """Group and cap findings by category for detailed report sections."""
    ranked = _rerank(insights)
    grouped: dict[str, list[dict]] = {category: [] for category in CATEGORIES}
    for insight in ranked:
        category = str(insight.get("category"))
        if category not in grouped:
            continue
        if len(grouped[category]) >= max_per_category:
            continue
        grouped[category].append(insight)
    return grouped


def curate_insights(
    raw_insights: list[dict],
    max_summary: int = 5,
    max_per_category: int = 3,
) -> dict[str, Any]:
    """Curate raw detector findings into a concise executive payload."""
    raw_count = len(raw_insights)
    filtered = filter_noisy_insights(raw_insights)
    filtered_ranked = _rerank(filtered)
    deduped = deduplicate_insights(filtered_ranked)
    deduped_ranked = _rerank(deduped)
    executive_candidates = limit_repeated_zones(deduped_ranked, max_per_zone=1)
    executive_summary = apply_category_diversity(
        executive_candidates,
        max_summary=max_summary,
        max_per_category=2,
    )
    insights_by_category = group_insights_by_category(deduped_ranked, max_per_category=max_per_category)

    return {
        "executive_summary_insights": executive_summary,
        "insights_by_category": insights_by_category,
        "curation_metadata": {
            "raw_count": raw_count,
            "post_filter_count": len(filtered),
            "post_dedup_count": len(deduped_ranked),
            "executive_summary_count": len(executive_summary),
            "max_summary": max_summary,
            "max_per_category": max_per_category,
        },
        "curated_insights": deduped_ranked,
    }

