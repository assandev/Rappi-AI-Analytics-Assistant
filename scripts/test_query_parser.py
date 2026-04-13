"""Diagnostic harness for LLM parser -> JSON -> Pydantic validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.query_parser import parse_question_to_json
from app.services.query_validator import validate_parsed_query


TEST_QUESTIONS = [
    "Which are the top 5 zones with highest Lead Penetration this week?",
    "Compare Perfect Orders between Wealthy and Non Wealthy in Mexico.",
    "Show the evolution of Gross Profit UE in Chapinero over the last 8 weeks.",
    "What is the average Lead Penetration by country?",
    "Which zones have high Lead Penetration but low Perfect Orders?",
    "Which zones are growing fastest in orders over the last 5 weeks and what could explain that growth?",
]


def print_separator(title: str) -> None:
    """Print section separator."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def run_single_test(question: str) -> bool:
    """Execute parser + validator flow for one question."""
    print_separator("QUESTION")
    print(question)
    try:
        payload = parse_question_to_json(question)
        print_separator("RAW PARSED PAYLOAD")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        validated = validate_parsed_query(payload)
        print_separator("VALIDATION RESULT")
        print("PASS")
        print_separator("VALIDATED MODEL")
        print(type(validated).__name__)
        print(validated.model_dump_json(indent=2))
        return True
    except Exception as exc:  # broad for diagnostics mode
        print_separator("VALIDATION RESULT")
        print("FAIL")
        print_separator("ERROR")
        print(f"{type(exc).__name__}: {exc}")
        return False


def main() -> None:
    """Run diagnostics for all test questions."""
    print_separator("PARSER HARNESS START")
    passed = 0
    failed = 0

    for idx, question in enumerate(TEST_QUESTIONS, start=1):
        print_separator(f"TEST CASE {idx}")
        success = run_single_test(question)
        if success:
            passed += 1
        else:
            failed += 1

    print_separator("SUMMARY")
    print(f"Total tests: {len(TEST_QUESTIONS)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()

