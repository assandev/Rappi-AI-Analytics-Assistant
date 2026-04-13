"""Sequential validation of conversational follow-up memory behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.execution import execute_query
from app.services.query_parser import parse_question_to_json
from app.services.query_validator import validate_parsed_query
from src.conversation import ConversationState, build_contextual_parser_input, is_follow_up_question


TEST_CASES = [
    "What is the average Lead Penetration by country?",
    "What about in Mexico?",
    "Which are the top 5 zones with highest Lead Penetration this week?",
    "Only Wealthy zones.",
]


def print_separator(title: str) -> None:
    """Print simple section separator."""
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


def load_datasets() -> dict[str, pd.DataFrame]:
    """Load normalized datasets from processed folder."""
    processed_dir = PROJECT_ROOT / "data" / "processed"
    return {
        "metrics_long": pd.read_csv(processed_dir / "metrics_long.csv"),
        "orders_long": pd.read_csv(processed_dir / "orders_long.csv"),
    }


def _contains_ci(value: Any, token: str) -> bool:
    """Case-insensitive containment helper."""
    return token.lower() in str(value or "").lower()


def run_case(
    index: int,
    question: str,
    state: ConversationState,
    datasets: dict[str, pd.DataFrame],
    previous_validated: dict[str, Any] | None,
) -> tuple[bool, dict[str, Any]]:
    """Run one case and return pass/fail plus diagnostic payload."""
    follow_up_detected = is_follow_up_question(question)
    parser_input = build_contextual_parser_input(question, state)
    contextual_parser_input_used = parser_input != question.strip()
    contextual_parse_fallback_used = False

    try:
        parsed_payload = parse_question_to_json(parser_input)
    except Exception:
        if not contextual_parser_input_used:
            raise
        parsed_payload = parse_question_to_json(question)
        contextual_parse_fallback_used = True

    validated = validate_parsed_query(parsed_payload)
    validated_dump = validated.model_dump(mode="json")
    execution_result = execute_query(validated, datasets)

    state.last_user_question = question
    state.last_validated_query = validated_dump
    state.last_execution_result = execution_result

    checks: list[tuple[str, bool]] = []
    if index == 1:
        checks.append(("follow_up=False", follow_up_detected is False))
        checks.append(("intent=aggregation", validated_dump.get("intent") == "aggregation"))
    elif index == 2:
        checks.append(("follow_up=True", follow_up_detected is True))
        checks.append(
            (
                "metric preserved from case 1",
                previous_validated is not None
                and validated_dump.get("metric") == previous_validated.get("metric"),
            )
        )
        checks.append(
            (
                "Mexico applied in geography filters",
                any(
                    _contains_ci(validated_dump.get("filters", {}).get(key), "mex")
                    for key in ("country", "city", "zone")
                ),
            )
        )
    elif index == 3:
        checks.append(("follow_up=False", follow_up_detected is False))
        checks.append(("intent=top_n_ranking", validated_dump.get("intent") == "top_n_ranking"))
    elif index == 4:
        checks.append(("follow_up=True", follow_up_detected is True))
        checks.append(
            (
                "metric preserved from case 3",
                previous_validated is not None
                and validated_dump.get("metric") == previous_validated.get("metric"),
            )
        )
        checks.append(
            (
                "zone_type set to Wealthy",
                _contains_ci(validated_dump.get("filters", {}).get("zone_type"), "wealthy"),
            )
        )

    passed = all(result for _, result in checks)
    diagnostics = {
        "question": question,
        "follow_up_detected": follow_up_detected,
        "contextual_parser_input_used": contextual_parser_input_used,
        "contextual_parse_fallback_used": contextual_parse_fallback_used,
        "parsed_payload": parsed_payload,
        "validated_query": validated_dump,
        "checks": [{"name": name, "passed": result} for name, result in checks],
        "passed": passed,
    }
    return passed, diagnostics


def main() -> None:
    """Run the 4-case sequential memory validation."""
    load_dotenv()
    datasets = load_datasets()
    state = ConversationState()

    print_separator("FOLLOW-UP MEMORY TEST START")
    passed_count = 0
    previous_validated: dict[str, Any] | None = None

    for idx, question in enumerate(TEST_CASES, start=1):
        print_separator(f"CASE {idx}")
        print(question)

        try:
            passed, diagnostics = run_case(idx, question, state, datasets, previous_validated)
            print(json.dumps(diagnostics, indent=2, ensure_ascii=False, default=str))
            if passed:
                print("RESULT: PASS")
                passed_count += 1
            else:
                print("RESULT: FAIL")
            previous_validated = diagnostics["validated_query"]
        except Exception as exc:
            print(f"RESULT: FAIL ({type(exc).__name__}: {exc})")

    failed_count = len(TEST_CASES) - passed_count
    print_separator("SUMMARY")
    print(f"Total: {len(TEST_CASES)}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")

    if failed_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
