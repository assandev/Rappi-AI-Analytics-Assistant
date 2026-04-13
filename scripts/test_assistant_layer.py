"""Deterministic checks for assistant additive layer."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.assistant import enrich_question_with_business_context, generate_suggestions


@dataclass
class FakeIntent:
    value: str


@dataclass
class FakeQuery:
    intent: FakeIntent


def print_separator(title: str) -> None:
    print("\n" + "=" * 86)
    print(title)
    print("=" * 86)


def run_context_awareness_tests() -> tuple[int, int]:
    tests = [
        (
            "Which are the problematic zones?",
            "Clarification: Which zones have low Perfect Orders or low Gross Profit UE this week?",
        ),
        (
            "¿Cuáles son las zonas problemáticas?",
            "Clarification: Which zones have low Perfect Orders or low Gross Profit UE this week?",
        ),
        (
            "Show Lead Penetration by country",
            "Show Lead Penetration by country",
        ),
    ]

    passed = 0
    failed = 0

    print_separator("CONTEXT AWARENESS")
    for question, expected_contains in tests:
        enriched = enrich_question_with_business_context(question)
        ok = expected_contains in enriched
        status = "PASS" if ok else "FAIL"
        print(f"{status} | input={question}")
        print(f"  output={enriched}")
        if not ok:
            print(f"  expected_contains={expected_contains}")
        if ok:
            passed += 1
        else:
            failed += 1

    return passed, failed


def run_suggestions_tests() -> tuple[int, int]:
    expected_by_intent = {
        "top_n_ranking": "Compare these results by zone type (Wealthy vs Non Wealthy)",
        "aggregation": "Break this metric down by zone for more granularity",
        "trend_analysis": "Compare this trend across multiple zones",
        "group_comparison": "Analyze how this comparison evolves over time",
        "multivariable_filter": "Analyze trends for these zones over time",
        "growth_analysis": "Check if growth is sustainable over a longer time window",
    }

    base_result = {"metadata": {"empty_result": False}, "rows": [{"zone": "x"}]}
    empty_result = {"metadata": {"empty_result": True}, "rows": []}

    passed = 0
    failed = 0

    print_separator("SUGGESTIONS")
    for intent_name, expected_first in expected_by_intent.items():
        query = FakeQuery(intent=FakeIntent(value=intent_name))
        suggestions = generate_suggestions(query, base_result)
        ok = len(suggestions) == 3 and suggestions[0] == expected_first
        status = "PASS" if ok else "FAIL"
        print(f"{status} | intent={intent_name}")
        print(f"  suggestions={json.dumps(suggestions, ensure_ascii=False)}")
        if ok:
            passed += 1
        else:
            failed += 1

    fallback_suggestions = generate_suggestions({"intent": "unknown_intent"}, base_result)
    fallback_ok = len(fallback_suggestions) == 3 and fallback_suggestions[0].startswith("Explore this metric")
    print(f"{'PASS' if fallback_ok else 'FAIL'} | fallback_intent")
    if fallback_ok:
        passed += 1
    else:
        failed += 1

    empty_suggestions = generate_suggestions(FakeQuery(intent=FakeIntent(value="top_n_ranking")), empty_result)
    empty_ok = len(empty_suggestions) == 3 and empty_suggestions[0].startswith("Remove one filter")
    print(f"{'PASS' if empty_ok else 'FAIL'} | empty_result_override")
    if empty_ok:
        passed += 1
    else:
        failed += 1

    return passed, failed


def main() -> None:
    total_passed = 0
    total_failed = 0

    passed, failed = run_context_awareness_tests()
    total_passed += passed
    total_failed += failed

    passed, failed = run_suggestions_tests()
    total_passed += passed
    total_failed += failed

    print_separator("SUMMARY")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")

    if total_failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

