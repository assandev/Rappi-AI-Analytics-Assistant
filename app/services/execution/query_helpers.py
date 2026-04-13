"""Reusable dataframe helpers for deterministic query execution."""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd


REQUIRED_DATASET_KEYS = ("metrics_long", "orders_long")
FILTER_FIELDS = ("country", "city", "zone", "zone_type", "zone_prioritization")
BASE_REQUIRED_COLUMNS = ("country", "city", "zone", "metric", "week", "value")


def validate_datasets(datasets: dict[str, pd.DataFrame]) -> None:
    """Validate required datasets exist and have the minimum expected shape."""
    if not isinstance(datasets, dict):
        raise ValueError("datasets must be a dictionary of pandas DataFrames.")

    missing = [key for key in REQUIRED_DATASET_KEYS if key not in datasets]
    if missing:
        raise ValueError(f"datasets is missing required keys: {missing}")

    for key in REQUIRED_DATASET_KEYS:
        dataframe = datasets[key]
        if not isinstance(dataframe, pd.DataFrame):
            raise ValueError(f"datasets['{key}'] must be a pandas DataFrame.")
        ensure_required_columns(dataframe, BASE_REQUIRED_COLUMNS, context=key)


def ensure_required_columns(
    dataframe: pd.DataFrame, required_cols: Iterable[str], context: str
) -> None:
    """Raise a clear error when required columns are missing."""
    missing = [column for column in required_cols if column not in dataframe.columns]
    if missing:
        raise ValueError(f"{context} is missing required columns: {missing}")


def get_metric_dataframe(metric: str, datasets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Select base dataframe by metric routing rule."""
    if not isinstance(metric, str) or not metric.strip():
        raise ValueError("metric must be a non-empty string.")

    if metric.strip().lower() == "orders":
        return datasets["orders_long"]
    return datasets["metrics_long"]


def _filters_to_dict(filters: Any) -> dict[str, Any]:
    """Convert filters object/model into a regular dict."""
    if filters is None:
        return {}
    if isinstance(filters, dict):
        return dict(filters)
    if hasattr(filters, "model_dump"):
        return dict(filters.model_dump())
    raise ValueError("filters must be a dict-like object or a Pydantic model.")


def apply_filters(dataframe: pd.DataFrame, filters: Any) -> pd.DataFrame:
    """Apply non-null geography filters to dataframe."""
    filters_dict = _filters_to_dict(filters)
    filtered = dataframe

    for field in FILTER_FIELDS:
        value = filters_dict.get(field)
        if value is None:
            continue

        if field not in filtered.columns:
            raise ValueError(
                f"Cannot apply filter '{field}' because the selected dataset does not have that column."
            )

        value_str = str(value).strip().casefold()
        filtered = filtered.loc[
            filtered[field].astype(str).str.strip().str.casefold() == value_str
        ]

    return filtered.copy()


def filter_metric_rows(dataframe: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Filter dataframe rows to one metric value."""
    ensure_required_columns(dataframe, ("metric",), context="metric_filter")
    metric_value = metric.strip().casefold()
    filtered = dataframe.loc[
        dataframe["metric"].astype(str).str.strip().str.casefold() == metric_value
    ]
    return filtered.copy()


def select_snapshot_week(dataframe: pd.DataFrame, week: int | None) -> pd.DataFrame:
    """Select rows for a specific snapshot week; defaults to week 0."""
    ensure_required_columns(dataframe, ("week",), context="snapshot_week")
    target_week = 0 if week is None else int(week)
    week_numeric = pd.to_numeric(dataframe["week"], errors="coerce")
    selected = dataframe.loc[week_numeric == target_week]
    return selected.copy()


def select_last_n_weeks(dataframe: pd.DataFrame, last_n_weeks: int | None) -> pd.DataFrame:
    """Select rows in the [0, last_n_weeks-1] range."""
    ensure_required_columns(dataframe, ("week",), context="last_n_weeks")
    if last_n_weeks is None:
        raise ValueError("last_n_weeks is required for this operation.")
    if int(last_n_weeks) <= 0:
        raise ValueError("last_n_weeks must be a positive integer.")

    max_week = int(last_n_weeks) - 1
    week_numeric = pd.to_numeric(dataframe["week"], errors="coerce")
    selected = dataframe.loc[week_numeric.between(0, max_week, inclusive="both")]
    return selected.copy()


def aggregate_series(
    dataframe: pd.DataFrame, group_cols: list[str], agg: str | Any
) -> pd.DataFrame:
    """Aggregate value column by group columns using deterministic mapping."""
    ensure_required_columns(dataframe, list(group_cols) + ["value"], context="aggregate_series")

    agg_name = str(getattr(agg, "value", agg)).strip().lower()
    agg_map = {
        "mean": "mean",
        "sum": "sum",
        "min": "min",
        "max": "max",
        "median": "median",
        "count": "count",
    }
    if agg_name not in agg_map:
        raise ValueError(f"Unsupported aggregation: {agg_name}")

    if dataframe.empty:
        return pd.DataFrame(columns=group_cols + ["value"])

    aggregated = (
        dataframe.groupby(group_cols, as_index=False, dropna=False)["value"]
        .agg(agg_map[agg_name])
        .reset_index(drop=True)
    )
    return aggregated


def _to_primitive(value: Any) -> Any:
    """Convert pandas/numpy scalar values into Python-native values."""
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def to_rows(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert dataframe rows to JSON-friendly list of dicts."""
    records = dataframe.to_dict(orient="records")
    return [{key: _to_primitive(value) for key, value in row.items()} for row in records]

