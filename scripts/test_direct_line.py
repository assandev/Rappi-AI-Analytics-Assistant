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
from src.assistant import enrich_question_with_business_context, generate_suggestions
from src.conversation import ConversationState, build_contextual_parser_input, is_follow_up_question
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
    state: ConversationState,
    formatter_llm_callable: Callable[..., str],
    preview_rows: int,
) -> bool:
    """Run one end-to-end direct-line test case."""
    print_separator("QUESTION")
    print(question)

    try:
        original_question = question.strip()
        enriched_question = enrich_question_with_business_context(original_question)
        business_context_applied = enriched_question != original_question

        follow_up_detected = is_follow_up_question(original_question)
        parser_input = build_contextual_parser_input(enriched_question, state)
        contextual_parser_input_used = parser_input != enriched_question
        contextual_parse_fallback_used = False

        print_separator("MEMORY DIAGNOSTICS")
        print(f"follow_up_detected: {follow_up_detected}")
        print(f"contextual_parser_input_used: {contextual_parser_input_used}")
        print(f"business_context_applied: {business_context_applied}")
        if business_context_applied:
            print(f"enriched_question: {enriched_question}")
        if state.last_validated_query:
            print(f"previous_intent: {state.last_validated_query.get('intent')}")
        else:
            print("previous_intent: None")

        parse_inputs = [parser_input]
        if enriched_question != parser_input:
            parse_inputs.append(enriched_question)
        if original_question not in parse_inputs:
            parse_inputs.append(original_question)

        parsed_payload = None
        last_error: Exception | None = None
        for idx, candidate_input in enumerate(parse_inputs):
            try:
                parsed_payload = parse_question_to_json(candidate_input)
                if idx > 0:
                    contextual_parse_fallback_used = True
                break
            except Exception as exc:
                last_error = exc

        if parsed_payload is None:
            if last_error is not None:
                raise last_error
            raise RuntimeError("Parser failed to return payload.")

        print(f"contextual_parse_fallback_used: {contextual_parse_fallback_used}")
        print_separator("PARSED PAYLOAD")
        print(json.dumps(parsed_payload, indent=2, ensure_ascii=False))

        validated_query = validate_parsed_query(parsed_payload)
        validated_dump = validated_query.model_dump(mode="json")
        print_separator("VALIDATED QUERY MODEL")
        print(type(validated_query).__name__)
        print_separator("VALIDATED QUERY PAYLOAD")
        print(json.dumps(validated_dump, indent=2, ensure_ascii=False, default=str))

        execution_result = execute_query(validated_query, datasets)
        compact_result = compact_execution_result(execution_result, max_rows=preview_rows)
        print_separator("EXECUTION RESULT (COMPACT)")
        print(json.dumps(compact_result, indent=2, ensure_ascii=False, default=str))
        suggestions = generate_suggestions(validated_query, execution_result)
        print_separator("SUGGESTIONS")
        print(json.dumps(suggestions, indent=2, ensure_ascii=False))

        final_response = format_response_with_llm(
            question=original_question,
            execution_result=execution_result,
            llm_callable=formatter_llm_callable,
        )
        print_separator("FINAL RESPONSE")
        print(final_response)

        state.last_user_question = original_question
        state.last_validated_query = validated_dump
        state.last_execution_result = execution_result
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
    state = ConversationState()

    passed = 0
    failed = 0

    for idx, question in enumerate(questions, start=1):
        print_separator(f"TEST CASE {idx}")
        if run_single_test(question, datasets, state, formatter_llm_callable, args.preview_rows):
            passed += 1
        else:
            failed += 1

    print_separator("SUMMARY")
    print(f"Total tests: {len(questions)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
