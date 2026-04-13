"""Deterministic orchestration for automatic insights detection and ranking."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.insights.insight_curator import curate_insights
from src.insights.detectors import (
    detect_anomalies,
    detect_benchmarking_gaps,
    detect_concerning_trends,
    detect_metric_correlations,
    detect_opportunities,
)
from src.insights.schemas import InsightItem, InsightPayload


def _validate_datasets(datasets: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if "metrics_long" not in datasets or "orders_long" not in datasets:
        raise ValueError("datasets must include 'metrics_long' and 'orders_long'.")

    metrics_df = datasets["metrics_long"]
    orders_df = datasets["orders_long"]

    metric_required = {"country", "city", "zone", "zone_type", "metric", "week", "value"}
    order_required = {"country", "city", "zone", "metric", "week", "value"}

    missing_metric = metric_required - set(metrics_df.columns)
    missing_order = order_required - set(orders_df.columns)

    if missing_metric:
        raise ValueError(f"metrics_long missing required columns: {sorted(missing_metric)}")
    if missing_order:
        raise ValueError(f"orders_long missing required columns: {sorted(missing_order)}")

    return metrics_df, orders_df


def run_insight_engine(
    datasets: dict[str, pd.DataFrame],
    top_k_critical: int = 5,
) -> InsightPayload:
    """Execute detectors, curate findings, and return executive-ready payload."""
    metrics_df, orders_df = _validate_datasets(datasets)

    detected: list[InsightItem] = []
    detected.extend(detect_anomalies(metrics_df, orders_df))
    detected.extend(detect_concerning_trends(metrics_df, orders_df))
    detected.extend(detect_benchmarking_gaps(metrics_df, orders_df))
    detected.extend(detect_metric_correlations(metrics_df, orders_df))
    detected.extend(detect_opportunities(metrics_df, orders_df))

    curated = curate_insights(
        raw_insights=[dict(item) for item in detected],
        max_summary=min(5, max(3, int(top_k_critical))),
        max_per_category=3,
    )
    curated_insights = curated["curated_insights"]

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "insight_count": len(curated_insights),
        "executive_summary_insights": curated["executive_summary_insights"],
        "insights_by_category": curated["insights_by_category"],
        "curation_metadata": curated["curation_metadata"],
        "curated_insights": curated_insights,
    }
