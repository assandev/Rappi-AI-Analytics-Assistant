"""Detector for large week-over-week anomalies."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

from src.insights.schemas import InsightItem, make_insight


BASE_COLS = ["country", "city", "zone", "metric", "week", "value"]


def _prepare_base(metrics_df: pd.DataFrame, orders_df: pd.DataFrame) -> pd.DataFrame:
    metric_part = metrics_df[BASE_COLS].copy()
    orders_part = orders_df[BASE_COLS].copy()
    base = pd.concat([metric_part, orders_part], ignore_index=True)
    base["week"] = pd.to_numeric(base["week"], errors="coerce")
    base["value"] = pd.to_numeric(base["value"], errors="coerce")
    base = base.dropna(subset=["country", "city", "zone", "metric", "week", "value"])
    return base


def detect_anomalies(
    metrics_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    threshold: float = 0.10,
    max_insights: int = 250,
) -> list[InsightItem]:
    """Detect large week-over-week changes between week 1 and week 0."""
    base = _prepare_base(metrics_df, orders_df)
    base = base[base["week"].isin([0, 1])]
    if base.empty:
        return []

    grouped = (
        base.groupby(["country", "city", "zone", "metric", "week"], as_index=False)["value"]
        .mean()
        .pivot(index=["country", "city", "zone", "metric"], columns="week", values="value")
        .reset_index()
        .rename(columns={0: "week_0_value", 1: "week_1_value"})
    )

    if "week_0_value" not in grouped.columns or "week_1_value" not in grouped.columns:
        return []

    grouped = grouped.dropna(subset=["week_0_value", "week_1_value"]).copy()
    if grouped.empty:
        return []

    denominator = grouped["week_1_value"].abs()
    grouped["pct_change"] = np.where(
        denominator > 1e-9,
        (grouped["week_0_value"] - grouped["week_1_value"]) / denominator,
        np.nan,
    )
    grouped = grouped.dropna(subset=["pct_change"])
    grouped = grouped[grouped["pct_change"].abs() >= threshold].copy()
    if grouped.empty:
        return []

    grouped["severity_score"] = (grouped["pct_change"].abs() * 200.0).clip(upper=100.0)
    grouped = grouped.sort_values(by="severity_score", ascending=False).head(max_insights)

    insights: list[InsightItem] = []
    for _, row in grouped.iterrows():
        direction = "improvement" if row["pct_change"] > 0 else "deterioration"
        pct_change = float(row["pct_change"])
        week_0_value = float(row["week_0_value"])
        week_1_value = float(row["week_1_value"])
        metric = str(row["metric"])
        country = str(row["country"])
        city = str(row["city"])
        zone = str(row["zone"])

        insights.append(
            cast(
                InsightItem,
                make_insight(
                    category="anomalies",
                    title=f"Large WoW {direction} in {metric}",
                    metric=metric,
                    country=country,
                    city=city,
                    zone=zone,
                    severity_score=float(row["severity_score"]),
                    summary=(
                        f"{metric} in {zone} ({city}, {country}) shows a "
                        f"{pct_change * 100:.2f}% week-over-week {direction}."
                    ),
                    evidence={
                        "week_0_value": week_0_value,
                        "week_1_value": week_1_value,
                        "pct_change": pct_change,
                        "direction": direction,
                        "affected_zones_count": 1,
                    },
                    recommendation_hint=(
                        "Validate operational drivers behind this sharp change and confirm if the shift is sustainable."
                    ),
                ),
            )
        )

    return insights

