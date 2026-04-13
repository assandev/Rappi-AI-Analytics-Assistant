"""LLM-based parser that converts natural language questions into JSON payloads."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()


def _test_logs_enabled() -> bool:
    """Return whether debug logs should be printed for test runs."""
    return os.getenv("TEST_DEBUG_LOGS", "0").strip().lower() in {"1", "true", "yes", "on"}


def _debug_log(title: str, value: Any) -> None:
    """Print debug logs only when TEST_DEBUG_LOGS is enabled."""
    if not _test_logs_enabled():
        return
    print(f"\n[DEBUG][query_parser] {title}")
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
    else:
        print(value)


def build_system_prompt() -> str:
    "Dimension semantics:\n"
    "- country, city, zone are geographic dimensions.\n"
    "- zone_type and zone_prioritization are different business dimensions.\n"
    "- Do not move values from one dimension to another.\n"
    "- Wealthy and Non Wealthy are values of zone_type.\n"
    "- Only assign a value to zone_prioritization if the question explicitly refers to prioritization.\n\n"

    "Never do the following:\n"
    "- return null for required numeric params\n"
    "- populate the grouping dimension inside filters\n"
    "- place comparison values into unrelated filter fields\n"
    "- mix fields from different intents\n"
    "- invent aliases like top_n or explain_growth\n\n"

    """Build strict instructions for parser-only JSON generation."""
    return (
        "You are a strict query parser for an analytics chatbot.\n"
        "Your task is to convert a user question into EXACTLY ONE valid JSON object.\n"
        "Return JSON only.\n"
        "Do not return markdown.\n"
        "Do not return explanations.\n"
        "Do not return comments.\n"
        "Do not invent fields that are not explicitly allowed.\n\n"

        "Supported intents (choose exactly one):\n"
        "- top_n_ranking\n"
        "- group_comparison\n"
        "- trend_analysis\n"
        "- aggregation\n"
        "- multivariable_filter\n"
        "- growth_analysis\n\n"

        "Allowed top-level fields:\n"
        "- intent\n"
        "- metric\n"
        "- filters\n"
        "- time_scope\n"
        "- group_by\n"
        "- params\n"
        "- conditions\n\n"

        "Allowed filters fields:\n"
        "- country\n"
        "- city\n"
        "- zone\n"
        "- zone_type\n"
        "- zone_prioritization\n\n"

        "Important filter rules:\n"
        "- Filters must be an object.\n"
        "- Missing filters should be null, not booleans.\n"
        "- Never use true/false inside filters.\n"
        "- If a filter is not mentioned, set it to null.\n\n"

        "Allowed group_by values:\n"
        "- country\n"
        "- city\n"
        "- zone\n"
        "- zone_type\n"
        "- zone_prioritization\n\n"

        "Important group_by rule:\n"
        "- group_by must be a dimension name, not a list of group values.\n"
        "- Example: comparing Wealthy vs Non Wealthy means group_by='zone_type'.\n"
        "- Never output group_by as ['Wealthy', 'Non Wealthy'].\n\n"

        "Allowed sort order values:\n"
        "- asc\n"
        "- desc\n\n"

        "Allowed aggregation values:\n"
        "- mean\n"
        "- sum\n"
        "- min\n"
        "- max\n"
        "- median\n"
        "- count\n\n"

        "Allowed condition operators:\n"
        "- high\n"
        "- low\n"
        "- gt\n"
        "- lt\n"
        "- eq\n\n"

        "Time rules:\n"
        "- For snapshot intents, use time_scope.week = 0 unless another week is explicitly requested.\n"
        "- For trend_analysis and growth_analysis, use time_scope.last_n_weeks.\n"
        "- For growth_analysis, time_scope.week must be null.\n\n"

        "Intent-specific schema rules:\n"
        "- top_n_ranking:\n"
        "  - required: intent, metric, filters, time_scope, group_by, params\n"
        "  - params must contain exactly: n, order\n"
        "  - never use top_n\n"
        "  - do not use last_n_weeks\n"
        "  - default group_by is 'zone'\n\n"

        "- group_comparison:\n"
        "  - if group_by = X, then filters.X must be null\n"
        "  - never fix the grouping dimension inside filters\n"
        "  - compared values belong to the group_by dimension, not to unrelated filter fields\n"
        "  - Wealthy / Non Wealthy must map to zone_type\n"
        "  - required: intent, metric, filters, time_scope, group_by, params\n"
        "  - params must contain: aggregation\n"
        "  - group_by must be a dimension like 'zone_type', not the compared values\n"
        "  - do not use last_n_weeks\n\n"

        "- trend_analysis:\n"
        "  - required: intent, metric, filters, time_scope, params\n"
        "  - params must contain: aggregation\n"
        "  - last_n_weeks is required and must be between 2 and 9\n"
        "  - at least one filter should define the scope\n"
        "  - when a neighborhood or operational area is mentioned, prefer zone over city\n\n"

        "- aggregation:\n"
        "  - required: intent, metric, filters, time_scope, group_by, params\n"
        "  - params must contain: aggregation\n"
        "  - do not use last_n_weeks\n"
        "  - do not place booleans in filters to indicate grouping\n\n"

        "- multivariable_filter:\n"
        "  - required: intent, filters, time_scope, conditions, params\n"
        "  - do not use metric at the top level unless absolutely necessary\n"
        "  - conditions must be a list\n"
        "  - each condition must contain: metric, operator, value\n"
        "  - for operator high/low, value must be null\n"
        "  - for operator gt/lt/eq, value must be numeric\n"
        "  - params must contain: logical_operator\n"
        "  - do not use last_n_weeks\n\n"

        "- growth_analysis:\n"
        "  - if no number is specified for ranking by growth, default top_k to 5\n"
        "  - params.top_k must never be null\n"
        "  - required: intent, metric, filters, time_scope, params\n"
        "  - metric must be exactly 'Orders'\n"
        "  - last_n_weeks is required and must be between 2 and 9\n"
        "  - time_scope.week must be null\n"
        "  - params must contain exactly: top_k, include_driver_analysis\n"
        "  - never use explain_growth\n\n"

        "If uncertain, return the simplest schema-valid JSON for the most likely intent.\n\n"

        "Canonical examples:\n\n"

        "Example 1\n"
        "Question: Which are the top 5 zones with highest Lead Penetration this week?\n"
        "JSON:\n"
        "{\n"
        '  "intent": "top_n_ranking",\n'
        '  "metric": "Lead Penetration",\n'
        '  "filters": {\n'
        '    "country": null,\n'
        '    "city": null,\n'
        '    "zone": null,\n'
        '    "zone_type": null,\n'
        '    "zone_prioritization": null\n'
        "  },\n"
        '  "time_scope": {\n'
        '    "week": 0,\n'
        '    "last_n_weeks": null\n'
        "  },\n"
        '  "group_by": "zone",\n'
        '  "params": {\n'
        '    "n": 5,\n'
        '    "order": "desc"\n'
        "  }\n"
        "}\n\n"

        "Example 2\n"
        "Question: Compare Perfect Orders between Wealthy and Non Wealthy in Mexico.\n"
        "JSON:\n"
        "{\n"
        '  "intent": "group_comparison",\n'
        '  "metric": "Perfect Orders",\n'
        '  "filters": {\n'
        '    "country": "Mexico",\n'
        '    "city": null,\n'
        '    "zone": null,\n'
        '    "zone_type": null,\n'
        '    "zone_prioritization": null\n'
        "  },\n"
        '  "time_scope": {\n'
        '    "week": 0,\n'
        '    "last_n_weeks": null\n'
        "  },\n"
        '  "group_by": "zone_type",\n'
        '  "params": {\n'
        '    "aggregation": "mean"\n'
        "  }\n"
        "}\n\n"

        "Example 3\n"
        "Question: Show the evolution of Gross Profit UE in Chapinero over the last 8 weeks.\n"
        "JSON:\n"
        "{\n"
        '  "intent": "trend_analysis",\n'
        '  "metric": "Gross Profit UE",\n'
        '  "filters": {\n'
        '    "country": null,\n'
        '    "city": null,\n'
        '    "zone": "Chapinero",\n'
        '    "zone_type": null,\n'
        '    "zone_prioritization": null\n'
        "  },\n"
        '  "time_scope": {\n'
        '    "week": null,\n'
        '    "last_n_weeks": 8\n'
        "  },\n"
        '  "params": {\n'
        '    "aggregation": "mean"\n'
        "  }\n"
        "}\n\n"

        "Example 4\n"
        "Question: What is the average Lead Penetration by country?\n"
        "JSON:\n"
        "{\n"
        '  "intent": "aggregation",\n'
        '  "metric": "Lead Penetration",\n'
        '  "filters": {\n'
        '    "country": null,\n'
        '    "city": null,\n'
        '    "zone": null,\n'
        '    "zone_type": null,\n'
        '    "zone_prioritization": null\n'
        "  },\n"
        '  "time_scope": {\n'
        '    "week": 0,\n'
        '    "last_n_weeks": null\n'
        "  },\n"
        '  "group_by": "country",\n'
        '  "params": {\n'
        '    "aggregation": "mean"\n'
        "  }\n"
        "}\n\n"

        "Example 5\n"
        "Question: Which zones have high Lead Penetration but low Perfect Orders?\n"
        "JSON:\n"
        "{\n"
        '  "intent": "multivariable_filter",\n'
        '  "filters": {\n'
        '    "country": null,\n'
        '    "city": null,\n'
        '    "zone": null,\n'
        '    "zone_type": null,\n'
        '    "zone_prioritization": null\n'
        "  },\n"
        '  "time_scope": {\n'
        '    "week": 0,\n'
        '    "last_n_weeks": null\n'
        "  },\n"
        '  "conditions": [\n'
        "    {\n"
        '      "metric": "Lead Penetration",\n'
        '      "operator": "high",\n'
        '      "value": null\n'
        "    },\n"
        "    {\n"
        '      "metric": "Perfect Orders",\n'
        '      "operator": "low",\n'
        '      "value": null\n'
        "    }\n"
        "  ],\n"
        '  "params": {\n'
        '    "logical_operator": "and"\n'
        "  }\n"
        "}\n\n"

        "Example 6\n"
        "Question: Which zones are growing fastest in orders over the last 5 weeks and what could explain that growth?\n"
        "JSON:\n"
        "{\n"
        '  "intent": "growth_analysis",\n'
        '  "metric": "Orders",\n'
        '  "filters": {\n'
        '    "country": null,\n'
        '    "city": null,\n'
        '    "zone": null,\n'
        '    "zone_type": null,\n'
        '    "zone_prioritization": null\n'
        "  },\n"
        '  "time_scope": {\n'
        '    "week": null,\n'
        '    "last_n_weeks": 5\n'
        "  },\n"
        '  "params": {\n'
        '    "top_k": 5,\n'
        '    "include_driver_analysis": true\n'
        "  }\n"
        "}\n"
    )


def strip_json_fences(text: str) -> str:
    """Remove accidental markdown code fences around JSON."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def get_llm_client() -> OpenAI:
    """Create an OpenAI-compatible client from environment settings."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required.")

    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def parse_question_to_json(
    question: str, conversation_context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Parse a natural-language question into structured JSON payload."""
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    _provider = os.getenv("LLM_PROVIDER", "openai")

    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string.")

    user_payload: dict[str, Any] = {"question": question.strip()}
    if conversation_context:
        user_payload["conversation_context"] = conversation_context

    client = get_llm_client()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    )

    raw_text = response.choices[0].message.content if response.choices else None
    if not raw_text:
        raise RuntimeError("LLM returned an empty response.")
    _debug_log("RAW LLM OUTPUT", raw_text)

    cleaned_text = strip_json_fences(raw_text)
    try:
        parsed = json.loads(cleaned_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse LLM output as JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("Parsed LLM output must be a JSON object.")
    _debug_log("PARSED PAYLOAD", parsed)
    return parsed
