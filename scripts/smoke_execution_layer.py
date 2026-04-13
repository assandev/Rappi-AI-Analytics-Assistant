"""Manual smoke check for deterministic execution layer."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.schemas import (
    AggregationQuery,
    ConditionOperator,
    GroupBy,
    GroupComparisonQuery,
    GrowthAnalysisQuery,
    MetricCondition,
    MultivariableFilterQuery,
    QueryFilters,
    TimeScope,
    TopNRankingQuery,
    TrendAnalysisQuery,
)
from app.services.execution import execute_query


def load_datasets() -> dict[str, pd.DataFrame]:
    """Load normalized datasets from data/processed."""
    processed_dir = PROJECT_ROOT / "data" / "processed"
    return {
        "metrics_long": pd.read_csv(processed_dir / "metrics_long.csv"),
        "orders_long": pd.read_csv(processed_dir / "orders_long.csv"),
    }


def main() -> None:
    datasets = load_datasets()

    test_queries = [
        TopNRankingQuery(metric="Lead Penetration"),
        GroupComparisonQuery(
            metric="Perfect Orders",
            group_by=GroupBy.ZONE_TYPE,
            filters=QueryFilters(country="MX"),
        ),
        TrendAnalysisQuery(
            metric="Gross Profit UE",
            filters=QueryFilters(country="CO"),
            time_scope=TimeScope(week=None, last_n_weeks=6),
        ),
        AggregationQuery(metric="Lead Penetration", group_by=GroupBy.COUNTRY),
        MultivariableFilterQuery(
            conditions=[
                MetricCondition(metric="Lead Penetration", operator=ConditionOperator.HIGH),
                MetricCondition(metric="Perfect Orders", operator=ConditionOperator.LOW),
            ]
        ),
        GrowthAnalysisQuery(time_scope=TimeScope(week=None, last_n_weeks=5)),
    ]

    required_keys = {"intent", "result_type", "title", "metric", "rows", "metadata"}

    for query in test_queries:
        result = execute_query(query, datasets)
        missing = required_keys - set(result.keys())
        if missing:
            raise AssertionError(f"Missing output keys {missing} for intent={query.intent}")
        print(
            f"PASS | intent={query.intent.value} | result_type={result['result_type']} "
            f"| rows={len(result['rows'])}"
        )

    print("Smoke execution checks completed successfully.")


if __name__ == "__main__":
    main()

