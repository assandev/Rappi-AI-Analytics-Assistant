"""Router entrypoint for deterministic analytics execution."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

import pandas as pd
from dotenv import load_dotenv

from app.services.execution.intent_executors import (
    execute_aggregation,
    execute_group_comparison,
    execute_growth_analysis,
    execute_multivariable_filter,
    execute_top_n_ranking,
    execute_trend_analysis,
)
from app.services.execution.query_helpers import validate_datasets


load_dotenv()


EXECUTOR_REGISTRY: dict[str, Callable[[Any, dict[str, pd.DataFrame]], dict[str, Any]]] = {
    "top_n_ranking": execute_top_n_ranking,
    "group_comparison": execute_group_comparison,
    "trend_analysis": execute_trend_analysis,
    "aggregation": execute_aggregation,
    "multivariable_filter": execute_multivariable_filter,
    "growth_analysis": execute_growth_analysis,
}


def _test_logs_enabled() -> bool:
    """Return whether debug logs should be printed for test runs."""
    return os.getenv("TEST_DEBUG_LOGS", "0").strip().lower() in {"1", "true", "yes", "on"}


def _debug_log(title: str, value: Any) -> None:
    """Print debug logs only when TEST_DEBUG_LOGS is enabled."""
    if not _test_logs_enabled():
        return
    print(f"\n[DEBUG][query_executor] {title}")
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
    else:
        print(value)


def _resolve_intent(query: Any) -> str:
    """Extract string intent from validated query model."""
    intent = getattr(query, "intent", None)
    if intent is None:
        raise ValueError("query must contain an intent.")
    return getattr(intent, "value", str(intent))


def execute_query(query: Any, datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Execute a validated query against prepared datasets."""
    if query is None:
        raise ValueError("query must not be None.")

    validate_datasets(datasets)
    intent = _resolve_intent(query)

    executor = EXECUTOR_REGISTRY.get(intent)
    if executor is None:
        supported = ", ".join(sorted(EXECUTOR_REGISTRY.keys()))
        raise ValueError(f"Unsupported intent '{intent}'. Supported intents: {supported}")

    _debug_log("INTENT ROUTED", intent)
    result = executor(query, datasets)
    _debug_log("EXECUTION OUTPUT", result)
    return result
