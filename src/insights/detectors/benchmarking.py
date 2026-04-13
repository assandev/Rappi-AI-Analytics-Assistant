"""Detector for peer divergence benchmarking insights."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

from src.insights.schemas import InsightItem, make_insight


def _prepare_snapshot(metrics_df: pd.DataFrame, orders_df: pd.DataFrame) -> pd.DataFrame:
    metric_cols = ["country", "city", "zone", "zone_type", "metric", "week", "value"]
    order_cols = ["country", "city", "zone", "metric", "week", "value"]

    m = metrics_df[metric_cols].copy()
    o = orders_df[order_cols].copy()
    o["zone_type"] = None

    base = pd.concat([m, o[metric_cols]], ignore_index=True)
    base["week"] = pd.to_numeric(base["week"], errors="coerce")
    base["value"] = pd.to_numeric(base["value"], errors="coerce")
    base = base.dropna(subset=["country", "city", "zone", "metric", "week", "value"])
    base = base[base["week"] == 0].copy()
    if base.empty:
        return base

    return (
        base.groupby(["country", "city", "zone", "zone_type", "metric"], as_index=False)["value"]
        .mean()
        .reset_index(drop=True)
    )


def detect_benchmarking_gaps(
    metrics_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    min_peer_count: int = 5,
    gap_threshold: float = 0.15,
    max_insights: int = 200,
) -> list[InsightItem]:
    """Benchmark each zone against similar peers and flag large divergence."""
    snapshot = _prepare_snapshot(metrics_df, orders_df)
    if snapshot.empty:
        return []

    snapshot["peer_bucket"] = np.where(
        snapshot["zone_type"].notna() & (snapshot["zone_type"].astype(str).str.strip() != ""),
        snapshot["country"].astype(str) + "||" + snapshot["metric"].astype(str) + "||" + snapshot["zone_type"].astype(str),
        snapshot["country"].astype(str) + "||" + snapshot["metric"].astype(str) + "||ALL",
    )

    grouped = snapshot.groupby("peer_bucket")["value"].agg(["sum", "count"]).rename(
        columns={"sum": "peer_sum", "count": "peer_count"}
    )
    snapshot = snapshot.merge(grouped, on="peer_bucket", how="left")
    snapshot = snapshot[snapshot["peer_count"] >= min_peer_count].copy()
    if snapshot.empty:
        return []

    valid_peer_den = (snapshot["peer_count"] - 1).clip(lower=1)
    snapshot["peer_mean_excluding_self"] = (snapshot["peer_sum"] - snapshot["value"]) / valid_peer_den
    snapshot = snapshot[snapshot["peer_count"] > 1]
    snapshot = snapshot[snapshot["peer_mean_excluding_self"].abs() > 1e-9]
    if snapshot.empty:
        return []

    snapshot["gap_pct"] = (snapshot["value"] - snapshot["peer_mean_excluding_self"]) / snapshot[
        "peer_mean_excluding_self"
    ].abs()
    snapshot = snapshot[snapshot["gap_pct"].abs() >= gap_threshold].copy()
    if snapshot.empty:
        return []

    snapshot["severity_score"] = (snapshot["gap_pct"].abs() * 180.0).clip(upper=100.0)
    snapshot = snapshot.sort_values(by="severity_score", ascending=False).head(max_insights)

    insights: list[InsightItem] = []
    for _, row in snapshot.iterrows():
        gap_pct = float(row["gap_pct"])
        direction = "above" if gap_pct > 0 else "below"
        metric = str(row["metric"])
        country = str(row["country"])
        city = str(row["city"])
        zone = str(row["zone"])
        zone_type = None if pd.isna(row["zone_type"]) else str(row["zone_type"])
        peer_count = int(row["peer_count"])
        peer_mean = float(row["peer_mean_excluding_self"])
        zone_value = float(row["value"])

        insights.append(
            cast(
                InsightItem,
                make_insight(
                    category="benchmarking",
                    title=f"{zone} diverges from peers on {metric}",
                    metric=metric,
                    country=country,
                    city=city,
                    zone=zone,
                    severity_score=float(row["severity_score"]),
                    summary=(
                        f"{zone} is {abs(gap_pct) * 100:.2f}% {direction} peer average for {metric} "
                        f"within comparable zones in {country}."
                    ),
                    evidence={
                        "zone_value": zone_value,
                        "peer_mean": peer_mean,
                        "gap_pct": gap_pct,
                        "peer_count": peer_count,
                        "zone_type": zone_type,
                        "affected_zones_count": peer_count,
                    },
                    recommendation_hint=(
                        "Compare operating levers with in-group peers and replicate best practices where the gap is favorable."
                    ),
                ),
            )
        )

    return insights

