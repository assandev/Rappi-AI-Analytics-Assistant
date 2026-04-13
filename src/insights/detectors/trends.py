"""Detector for concerning deterioration trends."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

from src.insights.schemas import InsightItem, make_insight


HIGHER_IS_BETTER_OVERRIDES: dict[str, bool] = {
    "Restaurants Markdowns / GMV": False,
    "Non-Pro PTC > OP": False,
}


def _is_higher_better(metric: str) -> bool:
    return HIGHER_IS_BETTER_OVERRIDES.get(metric, True)


def _compute_longest_deterioration_run(metric_df: pd.DataFrame, higher_is_better: bool) -> dict | None:
    rows = metric_df.sort_values("week", ascending=False)[["week", "value"]].copy()
    rows["week"] = pd.to_numeric(rows["week"], errors="coerce")
    rows["value"] = pd.to_numeric(rows["value"], errors="coerce")
    rows = rows.dropna()
    if len(rows) < 4:
        return None

    best_run: dict | None = None
    run_len = 0
    run_start_week: int | None = None
    run_start_value: float | None = None
    run_end_week: int | None = None
    run_end_value: float | None = None

    values = rows.to_dict("records")
    for idx in range(len(values) - 1):
        older = values[idx]
        newer = values[idx + 1]
        older_week = int(older["week"])
        newer_week = int(newer["week"])
        older_value = float(older["value"])
        newer_value = float(newer["value"])

        if older_week - newer_week != 1:
            run_len = 0
            run_start_week = None
            run_start_value = None
            run_end_week = None
            run_end_value = None
            continue

        delta = newer_value - older_value
        deteriorating = delta < 0 if higher_is_better else delta > 0
        if deteriorating:
            if run_len == 0:
                run_start_week = older_week
                run_start_value = older_value
            run_len += 1
            run_end_week = newer_week
            run_end_value = newer_value
            if best_run is None or run_len > int(best_run["run_length"]):
                best_run = {
                    "run_length": run_len,
                    "start_week": run_start_week,
                    "end_week": run_end_week,
                    "start_value": run_start_value,
                    "end_value": run_end_value,
                }
        else:
            run_len = 0
            run_start_week = None
            run_start_value = None
            run_end_week = None
            run_end_value = None

    return best_run


def detect_concerning_trends(
    metrics_df: pd.DataFrame,
    _orders_df: pd.DataFrame,
    min_consecutive_steps: int = 3,
    max_insights: int = 200,
) -> list[InsightItem]:
    """Detect metrics with at least 3 consecutive deteriorating week-over-week steps."""
    required_cols = ["country", "city", "zone", "metric", "week", "value"]
    base = metrics_df[required_cols].copy()
    base["week"] = pd.to_numeric(base["week"], errors="coerce")
    base["value"] = pd.to_numeric(base["value"], errors="coerce")
    base = base.dropna(subset=required_cols)
    base = (
        base.groupby(["country", "city", "zone", "metric", "week"], as_index=False)["value"]
        .mean()
        .sort_values(["country", "city", "zone", "metric", "week"], ascending=[True, True, True, True, False])
    )
    if base.empty:
        return []

    insights: list[InsightItem] = []
    grouped = base.groupby(["country", "city", "zone", "metric"], dropna=False)
    for (country, city, zone, metric), group in grouped:
        metric_name = str(metric)
        run_info = _compute_longest_deterioration_run(group, _is_higher_better(metric_name))
        if not run_info:
            continue

        run_length = int(run_info["run_length"])
        if run_length < min_consecutive_steps:
            continue

        start_value = float(run_info["start_value"])
        end_value = float(run_info["end_value"])
        if abs(start_value) <= 1e-9:
            net_change_pct = np.nan
        else:
            net_change_pct = (end_value - start_value) / abs(start_value)

        magnitude_component = 0.0 if np.isnan(net_change_pct) else abs(float(net_change_pct)) * 120.0
        severity_score = min(100.0, run_length * 15.0 + magnitude_component)

        summary = (
            f"{metric_name} in {zone} ({city}, {country}) has deteriorated for "
            f"{run_length} consecutive weeks."
        )
        insights.append(
            cast(
                InsightItem,
                make_insight(
                    category="trends",
                    title=f"Concerning deterioration trend in {metric_name}",
                    metric=metric_name,
                    country=str(country),
                    city=str(city),
                    zone=str(zone),
                    severity_score=severity_score,
                    summary=summary,
                    evidence={
                        "run_length": run_length,
                        "start_week": int(run_info["start_week"]),
                        "end_week": int(run_info["end_week"]),
                        "start_value": start_value,
                        "end_value": end_value,
                        "net_change_pct": None if np.isnan(net_change_pct) else float(net_change_pct),
                        "higher_is_better": _is_higher_better(metric_name),
                        "affected_zones_count": 1,
                    },
                    recommendation_hint=(
                        "Prioritize a root-cause review over the full deterioration window and test targeted corrective actions."
                    ),
                ),
            )
        )

    insights.sort(key=lambda item: item["severity_score"], reverse=True)
    return insights[:max_insights]

