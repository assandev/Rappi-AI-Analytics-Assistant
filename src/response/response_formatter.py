"""LLM-based response formatter over deterministic execution outputs."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from src.config.metric_display import get_metric_display_config


NO_DATA_MESSAGE = "No matching data was found for your query."
SUPPORTED_INTENTS = {
    "top_n_ranking",
    "group_comparison",
    "trend_analysis",
    "aggregation",
    "multivariable_filter",
    "growth_analysis",
}


def build_response_system_prompt() -> str:
    """Build strict but insight-aware system prompt for response formatting."""
    return (
        "You are an analytics response formatter.\n"
        "Your job is to transform structured analytics results into clear, concise, and insightful business responses.\n\n"

        "Hard rules:\n"
        "- Use only facts explicitly present in the provided execution result.\n"
        "- Do not compute new values.\n"
        "- Do not infer missing data.\n"
        "- Never infer units or symbols.\n"
        "- Never add %, $, currency names, or unit symbols unless explicitly supported by metadata.display.\n"
        "- metadata.display is the single source of truth for value formatting.\n"
        "- If metadata.display has no special format, render plain numbers.\n"
        "- Do not change rankings, ordering, or raw values.\n"
        "- Do not add external knowledge or assumptions.\n"
        "- Do not mention system internals (parser, JSON, schema, model, pipeline).\n"
        "- Return plain text only (no markdown, no bullet points, no JSON).\n\n"

        "What you ARE allowed to do:\n"
        "- Summarize results.\n"
        "- Highlight the most important findings.\n"
        "- Compare values that are already present.\n"
        "- Point out large gaps, trends, or notable differences.\n"
        "- Provide a short interpretation based ONLY on the given data.\n\n"

        "Response guidelines:\n"
        "- Start with the most important insight.\n"
        "- Avoid just listing values.\n"
        "- Add 1–2 sentences of interpretation when relevant.\n"
        "- Keep answers concise but informative.\n\n"

        "Tone:\n"
        "- concise\n"
        "- business-friendly\n"
        "- analytical\n"
        "- direct"
    )


def compact_execution_result(execution_result: dict, max_rows: int = 8) -> dict:
    """Create a compact execution result safe for prompt inclusion."""
    if not isinstance(execution_result, dict):
        raise ValueError("execution_result must be a dictionary.")

    if max_rows <= 0:
        raise ValueError("max_rows must be greater than 0.")

    rows = execution_result.get("rows") or []
    if not isinstance(rows, list):
        rows = []

    truncated_rows = rows[:max_rows]
    metadata = dict(execution_result.get("metadata") or {})
    metadata["rows_returned_to_llm"] = len(truncated_rows)
    metadata["rows_truncated"] = len(rows) > max_rows
    metadata.setdefault("original_row_count", len(rows))

    return {
        "intent": execution_result.get("intent"),
        "result_type": execution_result.get("result_type"),
        "title": execution_result.get("title"),
        "metric": execution_result.get("metric"),
        "rows": truncated_rows,
        "metadata": metadata,
    }


def build_response_user_prompt(question: str, execution_result: dict) -> str:
    """Build user prompt with original question and compact execution result."""
    compact_result = compact_execution_result(execution_result)
    compact_json = json.dumps(compact_result, ensure_ascii=False, indent=2, default=str)
    return (
        "User question:\n"
        f"{question.strip()}\n\n"
        "Execution result (trusted deterministic output):\n"
        f"{compact_json}\n\n"
        "Write a concise answer using only the provided result. "
        "Do not add facts that are not explicitly present. "
        "Use metadata.display for any value formatting and do not infer units."
        "Focus on highlighting the most important takeaway, not listing all values."
    )


def _is_empty_result(execution_result: dict) -> bool:
    """Return True if execution result represents no matching data."""
    metadata = execution_result.get("metadata") or {}
    rows = execution_result.get("rows") or []
    return bool(metadata.get("empty_result", False)) or len(rows) == 0


def _looks_like_markdown(text: str) -> bool:
    """Detect markdown/codeblock style output that should trigger fallback."""
    stripped = text.strip()
    if stripped.startswith("```") or stripped.endswith("```"):
        return True
    if re.search(r"^\s*#{1,6}\s+", stripped, flags=re.MULTILINE):
        return True
    if re.search(r"^\s*[-*]\s+", stripped, flags=re.MULTILINE):
        return True
    return False


def _clean_plain_text(text: str) -> str:
    """Normalize whitespace for plain-text response."""
    cleaned = " ".join(text.split())
    return cleaned.strip()


def format_metric_value(value: Any, display_config: dict) -> str:
    """Format value using explicit display metadata only."""
    if value is None:
        return "N/A"
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return str(value)

    if numeric_value != numeric_value:  # NaN-safe check
        return "N/A"

    value_format = str(display_config.get("value_format", "number")).strip().lower()
    decimals = int(display_config.get("decimals", 2))

    if value_format == "integer":
        return str(int(round(numeric_value)))
    if value_format == "percentage_ratio":
        return f"{numeric_value * 100:.{decimals}f}%"
    return f"{numeric_value:.{decimals}f}"


def _resolve_display_config(execution_result: dict) -> dict:
    """Resolve base display config from metadata or safe metric default."""
    metadata = execution_result.get("metadata") or {}
    metric = str(execution_result.get("metric") or "").strip()
    metadata_display = metadata.get("display")

    if isinstance(metadata_display, dict) and "value_format" in metadata_display:
        return {
            "value_format": metadata_display.get("value_format", "number"),
            "decimals": int(metadata_display.get("decimals", 2)),
        }
    return get_metric_display_config(metric)


def _resolve_field_display_config(execution_result: dict, field_name: str) -> dict:
    """Resolve display config for a specific field in row outputs."""
    metadata = execution_result.get("metadata") or {}
    metadata_display = metadata.get("display")
    if isinstance(metadata_display, dict):
        fields = metadata_display.get("fields")
        if isinstance(fields, dict):
            field_config = fields.get(field_name)
            if isinstance(field_config, dict):
                return {
                    "value_format": field_config.get("value_format", "number"),
                    "decimals": int(field_config.get("decimals", 2)),
                }
    return _resolve_display_config(execution_result)


def _fallback_top_n(metric: str, rows: list[dict[str, Any]], display_config: dict) -> str:
    items = []
    for row in rows[:5]:
        label = row.get("zone") or row.get("country") or row.get("city") or row.get("group")
        value = row.get("value")
        if label is None:
            continue
        items.append(f"{label} ({format_metric_value(value, display_config)})")
    if not items:
        return NO_DATA_MESSAGE
    return f"Top results for {metric}: " + ", ".join(items) + "."


def _fallback_group_comparison(metric: str, rows: list[dict[str, Any]], display_config: dict) -> str:
    if not rows:
        return NO_DATA_MESSAGE
    if len(rows) == 1:
        row = rows[0]
        group = next((v for k, v in row.items() if k != "value"), "group")
        return f"For {metric}, {group} has value {format_metric_value(row.get('value'), display_config)}."
    row_a, row_b = rows[0], rows[1]
    group_key_a = next((k for k in row_a.keys() if k != "value"), "group")
    group_key_b = next((k for k in row_b.keys() if k != "value"), "group")
    return (
        f"For {metric}, {row_a.get(group_key_a)} is {format_metric_value(row_a.get('value'), display_config)} "
        f"vs {row_b.get(group_key_b)} at {format_metric_value(row_b.get('value'), display_config)}."
    )


def _fallback_trend(metric: str, rows: list[dict[str, Any]], display_config: dict) -> str:
    if not rows:
        return NO_DATA_MESSAGE
    newest = next((r for r in rows if r.get("week") == 0), rows[-1])
    oldest = rows[0]
    return (
        f"{metric} over time goes from week {oldest.get('week')} "
        f"({format_metric_value(oldest.get('value'), display_config)}) to week {newest.get('week')} "
        f"({format_metric_value(newest.get('value'), display_config)})."
    )


def _fallback_aggregation(metric: str, rows: list[dict[str, Any]], display_config: dict) -> str:
    if not rows:
        return NO_DATA_MESSAGE
    sample = []
    for row in rows[:4]:
        keys = [k for k in row.keys() if k != "value"]
        label = " / ".join(str(row[k]) for k in keys) if keys else "group"
        sample.append(f"{label}: {format_metric_value(row.get('value'), display_config)}")
    return f"{metric} grouped summary ({len(rows)} groups): " + "; ".join(sample) + "."


def _fallback_multivariable(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return NO_DATA_MESSAGE
    samples = []
    for row in rows[:3]:
        country = row.get("country", "N/A")
        city = row.get("city", "N/A")
        zone = row.get("zone", "N/A")
        samples.append(f"{country} / {city} / {zone}")
    return f"Found {len(rows)} matching zones. Sample matches: " + ", ".join(samples) + "."


def _fallback_growth(execution_result: dict, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return NO_DATA_MESSAGE
    items = []
    absolute_growth_display = _resolve_field_display_config(execution_result, "absolute_growth")
    growth_rate_display = _resolve_field_display_config(execution_result, "growth_rate")
    for row in rows[:5]:
        zone = row.get("zone", "N/A")
        growth = format_metric_value(row.get("absolute_growth"), absolute_growth_display)
        rate = format_metric_value(row.get("growth_rate"), growth_rate_display)
        items.append(f"{zone} (growth {growth}, rate {rate})")
    return "Top growth zones: " + ", ".join(items) + "."


def format_response_fallback(question: str, execution_result: dict) -> str:
    """Deterministic fallback formatter by intent and result content."""
    if not isinstance(execution_result, dict):
        return NO_DATA_MESSAGE
    if _is_empty_result(execution_result):
        return NO_DATA_MESSAGE

    intent = str(execution_result.get("intent") or "").strip()
    metric = str(execution_result.get("metric") or "metric").strip()
    rows = execution_result.get("rows") or []
    if not isinstance(rows, list):
        rows = []
    display_config = _resolve_display_config(execution_result)

    if intent == "top_n_ranking":
        return _fallback_top_n(metric, rows, display_config)
    if intent == "group_comparison":
        return _fallback_group_comparison(metric, rows, display_config)
    if intent == "trend_analysis":
        return _fallback_trend(metric, rows, display_config)
    if intent == "aggregation":
        return _fallback_aggregation(metric, rows, display_config)
    if intent == "multivariable_filter":
        return _fallback_multivariable(rows)
    if intent == "growth_analysis":
        return _fallback_growth(execution_result, rows)

    title = execution_result.get("title") or "Query result"
    if rows:
        return f"{title}: {len(rows)} rows returned."
    return NO_DATA_MESSAGE


def format_response_with_llm(
    question: str,
    execution_result: dict,
    llm_callable: Callable[..., str],
) -> str:
    """Format final response with LLM; fallback deterministically on any unsafe failure."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string.")
    if not isinstance(execution_result, dict):
        raise ValueError("execution_result must be a dictionary.")
    if not callable(llm_callable):
        raise ValueError("llm_callable must be callable.")

    if _is_empty_result(execution_result):
        return NO_DATA_MESSAGE

    system_prompt = build_response_system_prompt()
    user_prompt = build_response_user_prompt(question, execution_result)

    try:
        response_text = llm_callable(system_prompt=system_prompt, user_prompt=user_prompt)
        if not isinstance(response_text, str):
            return format_response_fallback(question, execution_result)

        cleaned = _clean_plain_text(response_text)
        if not cleaned:
            return format_response_fallback(question, execution_result)
        if _looks_like_markdown(cleaned):
            return format_response_fallback(question, execution_result)
        return cleaned
    except Exception:
        return format_response_fallback(question, execution_result)