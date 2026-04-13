"""Isolated test harness for src.response.response_formatter.format_response_with_llm."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Callable

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI


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
from src.response.response_formatter import compact_execution_result, format_response_with_llm


def print_separator(title: str) -> None:
    """Print section separator for readability."""
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def load_datasets() -> dict[str, pd.DataFrame]:
    """Load normalized analytical datasets."""
    processed = PROJECT_ROOT / "data" / "processed"
    return {
        "metrics_long": pd.read_csv(processed / "metrics_long.csv"),
        "orders_long": pd.read_csv(processed / "orders_long.csv"),
    }


def build_execution_samples(datasets: dict[str, pd.DataFrame]) -> list[tuple[str, str, dict]]:
    """Build realistic execution_result samples from current deterministic executor."""
    cases = [
        (
            "top_n_ranking",
            "Which are the top 5 zones with highest Lead Penetration this week?",
            TopNRankingQuery(metric="Lead Penetration"),
        ),
        (
            "group_comparison",
            "Compare Perfect Orders between Wealthy and Non Wealthy in Mexico.",
            GroupComparisonQuery(
                metric="Perfect Orders",
                group_by=GroupBy.ZONE_TYPE,
                filters=QueryFilters(country="MX"),
            ),
        ),
        (
            "trend_analysis",
            "Show the evolution of Gross Profit UE in Chapinero over the last 8 weeks.",
            TrendAnalysisQuery(
                metric="Gross Profit UE",
                filters=QueryFilters(zone="Chapinero"),
                time_scope=TimeScope(week=None, last_n_weeks=8),
            ),
        ),
        (
            "aggregation",
            "What is the average Lead Penetration by country?",
            AggregationQuery(metric="Lead Penetration", group_by=GroupBy.COUNTRY),
        ),
        (
            "multivariable_filter",
            "Which zones have high Lead Penetration but low Perfect Orders?",
            MultivariableFilterQuery(
                conditions=[
                    MetricCondition(metric="Lead Penetration", operator=ConditionOperator.HIGH),
                    MetricCondition(metric="Perfect Orders", operator=ConditionOperator.LOW),
                ]
            ),
        ),
        (
            "growth_analysis",
            "Which zones are growing fastest in orders over the last 5 weeks?",
            GrowthAnalysisQuery(time_scope=TimeScope(week=None, last_n_weeks=5)),
        ),
    ]

    samples: list[tuple[str, str, dict]] = []
    for intent_name, question, query in cases:
        result = execute_query(query, datasets)
        samples.append((intent_name, question, result))
    return samples


def build_real_llm_callable() -> Callable[..., str]:
    """Build real formatter LLM callable from environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for --real-llm mode.")

    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_FORMATTER_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    temperature = float(os.getenv("FORMATTER_TEMPERATURE", "0"))

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def _call(system_prompt: str, user_prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content if response.choices else "") or ""

    return _call


def mock_llm_ok(system_prompt: str, user_prompt: str) -> str:
    """Mock LLM that returns valid plain text."""
    return "Summary generated from provided deterministic results."


def mock_llm_markdown(system_prompt: str, user_prompt: str) -> str:
    """Mock LLM that returns markdown to force fallback."""
    return "```json {\"invalid\": true} ```"


def mock_llm_exception(system_prompt: str, user_prompt: str) -> str:
    """Mock LLM that raises exception to force fallback."""
    raise RuntimeError("Intentional mock error")


def looks_like_markdown(text: str) -> bool:
    """Check markdown/codeblock-like output."""
    stripped = text.strip()
    return stripped.startswith("```") or stripped.startswith("#") or stripped.startswith("- ")


def run_case(
    case_name: str,
    question: str,
    execution_result: dict,
    llm_callable: Callable[..., str],
    preview_rows: int,
) -> tuple[bool, str]:
    """Run one formatter test case and return status + response."""
    compact = compact_execution_result(execution_result, max_rows=preview_rows)
    print_separator(f"CASE: {case_name}")
    print("QUESTION:")
    print(question)
    print("\nEXECUTION RESULT (COMPACT):")
    print(json.dumps(compact, ensure_ascii=False, indent=2, default=str))

    response = format_response_with_llm(
        question=question,
        execution_result=execution_result,
        llm_callable=llm_callable,
    )
    print("\nFORMATTED RESPONSE:")
    print(response)

    passed = bool(response.strip()) and not looks_like_markdown(response)
    return passed, response


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Isolated test harness for response formatter.")
    parser.add_argument(
        "--real-llm",
        action="store_true",
        help="Use real LLM call from env vars instead of mock success callable.",
    )
    parser.add_argument(
        "--preview-rows",
        type=int,
        default=5,
        help="Rows shown in compact execution_result preview.",
    )
    return parser.parse_args()


def main() -> None:
    """Run isolated formatter tests."""
    load_dotenv()
    args = parse_args()

    datasets = load_datasets()
    samples = build_execution_samples(datasets)

    llm_callable = build_real_llm_callable() if args.real_llm else mock_llm_ok

    print_separator("FORMATTER TEST START")
    passed = 0
    failed = 0

    # 1) Main path over all intents
    for intent_name, question, execution_result in samples:
        ok, _ = run_case(
            case_name=f"{intent_name} | {'real-llm' if args.real_llm else 'mock-ok'}",
            question=question,
            execution_result=execution_result,
            llm_callable=llm_callable,
            preview_rows=args.preview_rows,
        )
        if ok:
            passed += 1
        else:
            failed += 1

    # 2) Fallback path: markdown response
    intent_name, question, execution_result = samples[0]
    ok, response = run_case(
        case_name=f"{intent_name} | fallback-markdown",
        question=question,
        execution_result=execution_result,
        llm_callable=mock_llm_markdown,
        preview_rows=args.preview_rows,
    )
    if ok and not looks_like_markdown(response):
        passed += 1
    else:
        failed += 1

    # 3) Fallback path: exception response
    ok, response = run_case(
        case_name=f"{intent_name} | fallback-exception",
        question=question,
        execution_result=execution_result,
        llm_callable=mock_llm_exception,
        preview_rows=args.preview_rows,
    )
    if ok and not looks_like_markdown(response):
        passed += 1
    else:
        failed += 1

    # 4) Empty-result deterministic response
    empty_result = dict(execution_result)
    empty_result["rows"] = []
    empty_meta = dict(empty_result.get("metadata") or {})
    empty_meta["empty_result"] = True
    empty_result["metadata"] = empty_meta
    ok, response = run_case(
        case_name=f"{intent_name} | empty-result",
        question=question,
        execution_result=empty_result,
        llm_callable=llm_callable,
        preview_rows=args.preview_rows,
    )
    if ok and response == "No matching data was found for your query.":
        passed += 1
    else:
        failed += 1

    print_separator("SUMMARY")
    total = len(samples) + 3
    print(f"Total tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()

