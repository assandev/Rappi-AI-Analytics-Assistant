"""Simple typed contracts for deterministic insights payloads."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


InsightCategory = Literal[
    "anomalies",
    "trends",
    "benchmarking",
    "correlations",
    "opportunities",
]


class InsightItem(TypedDict):
    """One normalized insight detected by deterministic rules."""

    category: InsightCategory
    title: str
    metric: str
    country: str | None
    city: str | None
    zone: str | None
    severity_score: float
    priority_score: float
    summary: str
    evidence: dict[str, Any]
    recommendation_hint: str
    confidence: NotRequired[Literal["high", "medium", "low"]]


class InsightPayload(TypedDict):
    """Engine output consumed by report generation."""

    generated_at: str
    insight_count: int
    executive_summary_insights: list[InsightItem]
    insights_by_category: dict[InsightCategory, list[InsightItem]]
    curation_metadata: dict[str, Any]
    curated_insights: list[InsightItem]


def make_insight(
    *,
    category: InsightCategory,
    title: str,
    metric: str,
    country: str | None,
    city: str | None,
    zone: str | None,
    severity_score: float,
    summary: str,
    evidence: dict[str, Any],
    recommendation_hint: str,
    confidence: Literal["high", "medium", "low"] | None = None,
) -> InsightItem:
    """Create a normalized insight item with safe score ranges."""
    bounded_severity = float(max(0.0, min(100.0, severity_score)))
    item: InsightItem = {
        "category": category,
        "title": title,
        "metric": metric,
        "country": country,
        "city": city,
        "zone": zone,
        "severity_score": round(bounded_severity, 2),
        "priority_score": 0.0,
        "summary": summary,
        "evidence": evidence,
        "recommendation_hint": recommendation_hint,
    }
    if confidence:
        item["confidence"] = confidence
    return item
