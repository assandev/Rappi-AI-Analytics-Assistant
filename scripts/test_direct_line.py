"""End-to-end direct-line test: question -> parser -> validation -> execution -> response."""

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

from app.services.execution import execute_query
from app.services.query_parser import parse_question_to_json
from app.services.query_validator import validate_parsed_query
from src.response.response_formatter import compact_execution_result, format_response_with_llm


TEST_QUESTIONS = [
    "Which are the top 5 zones with highest Lead Penetration this week?",
    "Compare Perfect Orders between Wealthy and Non Wealthy in Mexico.",
    "Show the evolution of Gross Profit UE in Chapinero over the last 8 weeks.",
    "What is the average Lead Penetration by country?",
    "Which zones have high Lead Penetration but low Perfect Orders?",
    "Which zones are growing fastest in orders over the last 5 weeks and what could explain that growth?",
]


def print_separator(title: str) -> None:
    """Print formatted section separator."""
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


def load_datasets() -> dict[str, pd.DataFrame]:
    """Load normalized datasets from data/processed."""
    processed_dir = PROJECT_ROOT / "data" / "processed"
    return {
        "metrics_long": pd.read_csv(processed_dir / "metrics_long.csv"),
        "orders_long": pd.read_csv(processed_dir / "orders_long.csv"),
    }


def _build_formatter_llm_callable() -> Callable[..., str]:
    """Build LLM callable with OpenAI-compatible client for response formatting."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_FORMATTER_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    temperature = float(os.getenv("FORMATTER_TEMPERATURE", "0"))

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def _llm_callable(system_prompt: str, user_prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = response.choices[0].message.content if response.choices else ""
        return text or ""

    return _llm_callable


def run_single_test(
    question: str,
    datasets: dict[str, pd.DataFrame],
    formatter_llm_callable: Callable[..., str],
    preview_rows: int,
) -> bool:
    """Run one end-to-end direct-line test case."""
    print_separator("QUESTION")
    print(question)

    try:
        parsed_payload = parse_question_to_json(question)
        print_separator("PARSED PAYLOAD")
        print(json.dumps(parsed_payload, indent=2, ensure_ascii=False))

        validated_query = validate_parsed_query(parsed_payload)
        print_separator("VALIDATED QUERY MODEL")
        print(type(validated_query).__name__)

        execution_result = execute_query(validated_query, datasets)
        compact_result = compact_execution_result(execution_result, max_rows=preview_rows)
        print_separator("EXECUTION RESULT (COMPACT)")
        print(json.dumps(compact_result, indent=2, ensure_ascii=False, default=str))

        final_response = format_response_with_llm(
            question=question,
            execution_result=execution_result,
            llm_callable=formatter_llm_callable,
        )
        print_separator("FINAL RESPONSE")
        print(final_response)
        return True
    except Exception as exc:
        print_separator("ERROR")
        print(f"{type(exc).__name__}: {exc}")
        return False


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for direct-line tests."""
    parser = argparse.ArgumentParser(
        description="Run end-to-end direct-line tests over parser/validator/executor/formatter."
    )
    parser.add_argument(
        "--question",
        action="append",
        help="Single question to test. Repeat flag for multiple questions.",
    )
    parser.add_argument(
        "--preview-rows",
        type=int,
        default=5,
        help="Rows to show in compact execution preview.",
    )
    return parser.parse_args()


def main() -> None:
    """Run end-to-end direct-line tests."""
    load_dotenv()

    args = parse_args()
    questions = args.question if args.question else TEST_QUESTIONS

    print_separator("DIRECT LINE TEST START")
    datasets = load_datasets()
    formatter_llm_callable = _build_formatter_llm_callable()

    passed = 0
    failed = 0

    for idx, question in enumerate(questions, start=1):
        print_separator(f"TEST CASE {idx}")
        if run_single_test(question, datasets, formatter_llm_callable, args.preview_rows):
            passed += 1
        else:
            failed += 1

    print_separator("SUMMARY")
    print(f"Total tests: {len(questions)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()

