"""Builders for consistent structured execution outputs."""

from __future__ import annotations

from typing import Any


def _normalize_metadata(rows: list[dict[str, Any]], metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Inject common metadata fields used across all result types."""
    normalized = dict(metadata or {})
    normalized.setdefault("row_count", len(rows))
    normalized.setdefault("empty_result", len(rows) == 0)
    return normalized


def build_table_result(
    intent: str,
    title: str,
    metric: str,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a tabular result payload."""
    return {
        "intent": intent,
        "result_type": "table",
        "title": title,
        "metric": metric,
        "rows": rows,
        "metadata": _normalize_metadata(rows, metadata),
    }


def build_timeseries_result(
    intent: str,
    title: str,
    metric: str,
    rows: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a time series result payload."""
    return {
        "intent": intent,
        "result_type": "timeseries",
        "title": title,
        "metric": metric,
        "rows": rows,
        "metadata": _normalize_metadata(rows, metadata),
    }

