"""Detector for practical metric-pair correlation signals."""

from __future__ import annotations

from typing import cast

import pandas as pd

from src.insights.schemas import InsightItem, make_insight


METRIC_PAIRS: list[tuple[str, str]] = [
    ("Lead Penetration", "Perfect Orders"),
    ("Perfect Orders", "Orders"),
    ("Gross Profit UE", "Orders"),
]


def _prepare_snapshot(metrics_df: pd.DataFrame, orders_df: pd.DataFrame) -> pd.DataFrame:
    metric_cols = ["country", "city", "zone", "metric", "week", "value"]
    m = metrics_df[metric_cols].copy()
    o = orders_df[metric_cols].copy()
    base = pd.concat([m, o], ignore_index=True)
    base["week"] = pd.to_numeric(base["week"], errors="coerce")
    base["value"] = pd.to_numeric(base["value"], errors="coerce")
    base = base.dropna(subset=["country", "city", "zone", "metric", "week", "value"])
    base = base[base["week"] == 0].copy()
    if base.empty:
        return base

    return (
        base.groupby(["country", "city", "zone", "metric"], as_index=False)["value"]
        .mean()
        .reset_index(drop=True)
    )


def detect_metric_correlations(
    metrics_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    min_sample_size: int = 8,
    corr_threshold: float = 0.45,
    max_insights: int = 100,
) -> list[InsightItem]:
    """Detect strong metric relationships across zones within each country."""
    snapshot = _prepare_snapshot(metrics_df, orders_df)
    if snapshot.empty:
        return []

    insights: list[InsightItem] = []
    for country, country_df in snapshot.groupby("country", dropna=False):
        wide = country_df.pivot_table(index=["city", "zone"], columns="metric", values="value", aggfunc="mean")
        if wide.empty:
            continue

        for metric_x, metric_y in METRIC_PAIRS:
            if metric_x not in wide.columns or metric_y not in wide.columns:
                continue

            pair_df = wide[[metric_x, metric_y]].dropna()
            sample_size = len(pair_df)
            if sample_size < min_sample_size:
                continue

            corr = pair_df[metric_x].corr(pair_df[metric_y])
            if pd.isna(corr) or abs(float(corr)) < corr_threshold:
                continue

            corr_value = float(corr)
            direction = "positive" if corr_value > 0 else "negative"
            severity = min(100.0, abs(corr_value) * 100.0 + min(20.0, sample_size * 0.5))
            country_name = str(country)

            insights.append(
                cast(
                    InsightItem,
                    make_insight(
                        category="correlations",
                        title=f"{metric_x} and {metric_y} show a strong {direction} relationship",
                        metric=f"{metric_x} vs {metric_y}",
                        country=country_name,
                        city=None,
                        zone=None,
                        severity_score=severity,
                        summary=(
                            f"In {country_name}, {metric_x} and {metric_y} are strongly {direction} "
                            f"across zones (r={corr_value:.2f})."
                        ),
                        evidence={
                            "metric_x": metric_x,
                            "metric_y": metric_y,
                            "correlation": corr_value,
                            "sample_size": sample_size,
                            "country": country_name,
                            "affected_zones_count": sample_size,
                        },
                        recommendation_hint=(
                            "Use this relationship to design coordinated actions and track both metrics together."
                        ),
                    ),
                )
            )

    insights.sort(key=lambda item: item["severity_score"], reverse=True)
    return insights[:max_insights]

