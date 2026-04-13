"""Intent-specific deterministic pandas executors."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.execution.query_helpers import (
    aggregate_series,
    apply_filters,
    ensure_required_columns,
    filter_metric_rows,
    get_metric_dataframe,
    select_last_n_weeks,
    select_snapshot_week,
    to_rows,
)
from app.services.execution.result_builders import build_table_result, build_timeseries_result
from src.config.metric_display import get_metric_display_config


GEO_KEYS = ["country", "city", "zone"]


def _intent_value(query: Any) -> str:
    intent = getattr(query, "intent", None)
    return getattr(intent, "value", str(intent))


def _metric_value(query: Any, default: str | None = None) -> str:
    metric = getattr(query, "metric", default)
    if not metric:
        return default or ""
    return str(metric)


def _metric_display_metadata(metric: str) -> dict[str, Any]:
    """Build standard display metadata for value fields."""
    return get_metric_display_config(metric)


def execute_aggregation(query: Any, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Execute aggregation intent on snapshot week."""
    metric = _metric_value(query)
    group_by = query.group_by.value
    aggregation = getattr(query.params, "aggregation", "mean")
    snapshot_week = query.time_scope.week

    dataframe = get_metric_dataframe(metric, datasets)
    ensure_required_columns(dataframe, [group_by, "metric", "week", "value"], "aggregation")

    dataframe = filter_metric_rows(dataframe, metric)
    dataframe = apply_filters(dataframe, query.filters)
    dataframe = select_snapshot_week(dataframe, snapshot_week)

    aggregated = aggregate_series(dataframe, [group_by], aggregation)
    aggregated = aggregated.sort_values(by=["value", group_by], ascending=[False, True]).reset_index(
        drop=True
    )

    rows = to_rows(aggregated)
    title = f"{metric} by {group_by}"
    return build_table_result(
        intent=_intent_value(query),
        title=title,
        metric=metric,
        rows=rows,
        metadata={
            "group_by": group_by,
            "aggregation": str(getattr(aggregation, "value", aggregation)),
            "week": snapshot_week,
            "display": _metric_display_metadata(metric),
        },
    )


def execute_top_n_ranking(query: Any, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Execute top-N ranking intent on snapshot week."""
    metric = _metric_value(query)
    group_by = query.group_by.value
    snapshot_week = query.time_scope.week
    n = int(query.params.n)
    order = getattr(query.params.order, "value", str(query.params.order)).lower()

    dataframe = get_metric_dataframe(metric, datasets)
    ensure_required_columns(dataframe, [group_by, "metric", "week", "value"], "top_n_ranking")

    dataframe = filter_metric_rows(dataframe, metric)
    dataframe = apply_filters(dataframe, query.filters)
    dataframe = select_snapshot_week(dataframe, snapshot_week)

    ranked = aggregate_series(dataframe, [group_by], "mean")
    ascending = order == "asc"
    ranked = ranked.sort_values(by=["value", group_by], ascending=[ascending, True]).reset_index(
        drop=True
    )
    ranked = ranked.head(n).copy()
    ranked.insert(0, "rank", range(1, len(ranked) + 1))

    rows = to_rows(ranked)
    title = f"Top {n} {group_by} by {metric}"
    return build_table_result(
        intent=_intent_value(query),
        title=title,
        metric=metric,
        rows=rows,
        metadata={
            "group_by": group_by,
            "aggregation": "mean",
            "order": order,
            "n": n,
            "week": snapshot_week,
            "display": _metric_display_metadata(metric),
        },
    )


def execute_group_comparison(query: Any, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Execute group comparison intent on snapshot week."""
    metric = _metric_value(query)
    group_by = query.group_by.value
    aggregation = getattr(query.params, "aggregation", "mean")
    snapshot_week = query.time_scope.week

    dataframe = get_metric_dataframe(metric, datasets)
    ensure_required_columns(dataframe, [group_by, "metric", "week", "value"], "group_comparison")

    dataframe = filter_metric_rows(dataframe, metric)
    dataframe = apply_filters(dataframe, query.filters)
    dataframe = select_snapshot_week(dataframe, snapshot_week)

    compared = aggregate_series(dataframe, [group_by], aggregation)
    compared = compared.sort_values(by=["value", group_by], ascending=[False, True]).reset_index(
        drop=True
    )

    rows = to_rows(compared)
    title = f"Comparison of {metric} by {group_by}"
    return build_table_result(
        intent=_intent_value(query),
        title=title,
        metric=metric,
        rows=rows,
        metadata={
            "group_by": group_by,
            "aggregation": str(getattr(aggregation, "value", aggregation)),
            "week": snapshot_week,
            "display": _metric_display_metadata(metric),
        },
    )


def execute_trend_analysis(query: Any, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Execute trend analysis intent over last N weeks."""
    metric = _metric_value(query)
    aggregation = getattr(query.params, "aggregation", "mean")
    last_n_weeks = query.time_scope.last_n_weeks

    dataframe = get_metric_dataframe(metric, datasets)
    ensure_required_columns(dataframe, ["metric", "week", "value"], "trend_analysis")

    dataframe = filter_metric_rows(dataframe, metric)
    dataframe = apply_filters(dataframe, query.filters)
    dataframe = select_last_n_weeks(dataframe, last_n_weeks)

    trend = aggregate_series(dataframe, ["week"], aggregation)
    trend["week"] = pd.to_numeric(trend["week"], errors="coerce")
    trend = trend.sort_values(by=["week"], ascending=False).reset_index(drop=True)

    rows = to_rows(trend)
    title = f"{metric} trend over last {last_n_weeks} weeks"
    return build_timeseries_result(
        intent=_intent_value(query),
        title=title,
        metric=metric,
        rows=rows,
        metadata={
            "aggregation": str(getattr(aggregation, "value", aggregation)),
            "last_n_weeks": last_n_weeks,
            "display": _metric_display_metadata(metric),
        },
    )


def _evaluate_condition_rows(metric_df: pd.DataFrame, condition: Any) -> pd.DataFrame:
    """Evaluate one multivariable condition and return matching geographies."""
    operator = getattr(condition.operator, "value", str(condition.operator)).lower()
    value = getattr(condition, "value", None)

    if metric_df.empty:
        return pd.DataFrame(columns=GEO_KEYS)

    if operator == "gt":
        matched = metric_df.loc[metric_df["value"] > float(value)]
    elif operator == "lt":
        matched = metric_df.loc[metric_df["value"] < float(value)]
    elif operator == "eq":
        matched = metric_df.loc[metric_df["value"] == float(value)]
    elif operator == "high":
        threshold = float(metric_df["value"].quantile(0.75))
        matched = metric_df.loc[metric_df["value"] >= threshold]
    elif operator == "low":
        threshold = float(metric_df["value"].quantile(0.25))
        matched = metric_df.loc[metric_df["value"] <= threshold]
    else:
        raise ValueError(f"Unsupported condition operator: {operator}")

    return matched[GEO_KEYS].drop_duplicates().reset_index(drop=True)


def execute_multivariable_filter(query: Any, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Minimal deterministic v1 for multivariable filtering across condition metrics."""
    snapshot_week = query.time_scope.week
    logical_operator = str(query.params.logical_operator).lower()
    condition_matches: list[pd.DataFrame] = []
    condition_labels: list[str] = []

    for condition in query.conditions:
        condition_metric = str(condition.metric)
        dataframe = get_metric_dataframe(condition_metric, datasets)
        ensure_required_columns(
            dataframe, GEO_KEYS + ["metric", "week", "value"], "multivariable_filter"
        )

        dataframe = filter_metric_rows(dataframe, condition_metric)
        dataframe = apply_filters(dataframe, query.filters)
        dataframe = select_snapshot_week(dataframe, snapshot_week)
        dataframe = aggregate_series(dataframe, GEO_KEYS, "mean")

        matched = _evaluate_condition_rows(dataframe, condition)
        matched["condition_metric"] = condition_metric
        condition_matches.append(matched)
        condition_labels.append(condition_metric)

    if not condition_matches:
        rows: list[dict[str, Any]] = []
    else:
        if logical_operator == "and":
            combined = condition_matches[0][GEO_KEYS].copy()
            for frame in condition_matches[1:]:
                combined = combined.merge(frame[GEO_KEYS], on=GEO_KEYS, how="inner")
            combined = combined.drop_duplicates()
        elif logical_operator == "or":
            combined = pd.concat(
                [frame[GEO_KEYS] for frame in condition_matches], ignore_index=True
            ).drop_duplicates()
        else:
            raise ValueError(f"Unsupported logical_operator: {logical_operator}")

        match_counts = (
            pd.concat(condition_matches, ignore_index=True)[GEO_KEYS + ["condition_metric"]]
            .drop_duplicates()
            .groupby(GEO_KEYS, as_index=False)["condition_metric"]
            .count()
            .rename(columns={"condition_metric": "matched_conditions"})
        )
        combined = combined.merge(match_counts, on=GEO_KEYS, how="left")
        combined = combined.sort_values(
            by=["matched_conditions", "country", "city", "zone"],
            ascending=[False, True, True, True],
        ).reset_index(drop=True)
        rows = to_rows(combined)

    title = "Multivariable filter matches"
    return build_table_result(
        intent=_intent_value(query),
        title=title,
        metric="MULTI_CONDITION",
        rows=rows,
        metadata={
            "logical_operator": logical_operator,
            "conditions": condition_labels,
            "week": snapshot_week,
            "display": _metric_display_metadata("MULTI_CONDITION"),
        },
    )


def execute_growth_analysis(query: Any, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Minimal deterministic v1 growth ranking for Orders."""
    last_n_weeks = query.time_scope.last_n_weeks
    top_k = int(query.params.top_k)
    include_driver_analysis = bool(query.params.include_driver_analysis)

    dataframe = get_metric_dataframe("Orders", datasets)
    ensure_required_columns(dataframe, ["zone", "metric", "week", "value"], "growth_analysis")

    dataframe = filter_metric_rows(dataframe, "Orders")
    dataframe = apply_filters(dataframe, query.filters)
    dataframe = select_last_n_weeks(dataframe, last_n_weeks)

    weekly = aggregate_series(dataframe, ["zone", "week"], "mean")
    if weekly.empty:
        rows: list[dict[str, Any]] = []
        oldest_week = None
    else:
        weekly["week"] = pd.to_numeric(weekly["week"], errors="coerce")
        oldest_week = int(weekly["week"].max())

        current = weekly.loc[weekly["week"] == 0, ["zone", "value"]].rename(
            columns={"value": "current_value"}
        )
        baseline = weekly.loc[weekly["week"] == oldest_week, ["zone", "value"]].rename(
            columns={"value": "baseline_value"}
        )
        growth = current.merge(baseline, on="zone", how="inner")
        growth["absolute_growth"] = growth["current_value"] - growth["baseline_value"]
        growth["growth_rate"] = growth.apply(
            lambda row: None
            if row["baseline_value"] in (0, None)
            else row["absolute_growth"] / abs(row["baseline_value"]),
            axis=1,
        )
        growth = growth.sort_values(by=["absolute_growth", "zone"], ascending=[False, True]).reset_index(
            drop=True
        )
        growth = growth.head(top_k)
        rows = to_rows(growth)

    title = f"Top {top_k} zones by Orders growth"
    return build_table_result(
        intent=_intent_value(query),
        title=title,
        metric="Orders",
        rows=rows,
        metadata={
            "top_k": top_k,
            "last_n_weeks": last_n_weeks,
            "oldest_week_in_window": oldest_week,
            "include_driver_analysis": include_driver_analysis,
            "display": {
                **_metric_display_metadata("Orders"),
                "fields": {
                    "current_value": {"value_format": "integer", "decimals": 0},
                    "baseline_value": {"value_format": "integer", "decimals": 0},
                    "absolute_growth": {"value_format": "integer", "decimals": 0},
                    "growth_rate": {"value_format": "percentage_ratio", "decimals": 2},
                },
            },
        },
    )
