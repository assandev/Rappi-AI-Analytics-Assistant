"""LLM-assisted executive markdown report generation from deterministic insights."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from src.insights.schemas import InsightPayload


def build_report_system_prompt() -> str:
    """Build strict report-writing prompt with no-invention rules."""
    return (
        "You are an executive analytics report writer.\n"
        "Your only input source is a deterministic insights payload.\n\n"
        "Hard rules:\n"
        "- Use only facts from the provided insights payload.\n"
        "- Do not invent findings, metrics, values, geographies, or causes.\n"
        "- Do not add external context.\n"
        "- If a category has no findings, explicitly state that there were no material findings.\n"
        "- Keep content concise, executive-friendly, and actionable.\n"
        "- Output valid Markdown only.\n\n"
        "Required structure:\n"
        "1) # Executive Summary\n"
        "2) # Insights by Category\n"
        "3) # Recommendations\n"
    )


def _compact_payload(payload: InsightPayload, max_per_category: int = 12) -> dict[str, Any]:
    grouped = {}
    for category, items in payload["insights_by_category"].items():
        grouped[category] = items[:max_per_category]
    return {
        "generated_at": payload["generated_at"],
        "insight_count": payload["insight_count"],
        "curation_metadata": payload["curation_metadata"],
        "executive_summary_insights": payload["executive_summary_insights"][:5],
        "insights_by_category": grouped,
    }


def build_report_user_prompt(payload: InsightPayload) -> str:
    """Build user prompt with compact deterministic payload."""
    compact = _compact_payload(payload)
    compact_json = json.dumps(compact, ensure_ascii=False, indent=2, default=str)
    return (
        "Build an executive Markdown report from this deterministic insights payload.\n"
        "Do not add findings that are not present.\n\n"
        f"{compact_json}"
    )


def _recommendations_from_insights(payload: InsightPayload, limit: int = 6) -> list[str]:
    seen: set[str] = set()
    recommendations: list[str] = []
    detail_flat: list[dict[str, Any]] = []
    for items in payload["insights_by_category"].values():
        detail_flat.extend(items)

    for insight in payload["executive_summary_insights"] + detail_flat:
        hint = str(insight.get("recommendation_hint", "")).strip()
        if hint and hint not in seen:
            seen.add(hint)
            recommendations.append(hint)
        if len(recommendations) >= limit:
            break
    return recommendations


def build_markdown_fallback(payload: InsightPayload) -> str:
    """Deterministic fallback report when LLM fails."""
    lines: list[str] = []
    lines.append("# Executive Summary")
    if payload["executive_summary_insights"]:
        for insight in payload["executive_summary_insights"][:5]:
            lines.append(
                f"- **{insight['title']}** ({insight['category']}, severity {insight['severity_score']:.1f}, "
                f"priority {insight['priority_score']:.1f}) - {insight['summary']}"
            )
    else:
        lines.append("- No material critical findings were detected in this run.")

    lines.append("")
    lines.append("# Insights by Category")
    for category in ["anomalies", "trends", "benchmarking", "correlations", "opportunities"]:
        lines.append(f"## {category.title()}")
        items = payload["insights_by_category"].get(category, [])
        if not items:
            lines.append("- No material findings detected.")
            continue
        for insight in items:
            location = " / ".join(
                [
                    part
                    for part in [
                        insight.get("country"),
                        insight.get("city"),
                        insight.get("zone"),
                    ]
                    if part
                ]
            )
            location_text = f" [{location}]" if location else ""
            lines.append(
                f"- **{insight['title']}**{location_text}: {insight['summary']} "
                f"(severity={insight['severity_score']:.1f}, priority={insight['priority_score']:.1f})"
            )

    lines.append("")
    lines.append("# Recommendations")
    recommendations = _recommendations_from_insights(payload)
    if recommendations:
        for recommendation in recommendations:
            lines.append(f"- {recommendation}")
    else:
        lines.append("- No recommendations available because no material findings were detected.")

    return "\n".join(lines).strip() + "\n"


def _looks_like_markdown(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("#")


def generate_markdown_report(
    payload: InsightPayload,
    llm_callable: Callable[..., str] | None,
) -> str:
    """Generate markdown report with LLM-first strategy and deterministic fallback."""
    if llm_callable is None:
        return build_markdown_fallback(payload)

    system_prompt = build_report_system_prompt()
    user_prompt = build_report_user_prompt(payload)

    try:
        markdown_text = llm_callable(system_prompt=system_prompt, user_prompt=user_prompt)
        if not isinstance(markdown_text, str) or not markdown_text.strip():
            return build_markdown_fallback(payload)
        if not _looks_like_markdown(markdown_text):
            return build_markdown_fallback(payload)
        return markdown_text.strip() + "\n"
    except Exception:
        return build_markdown_fallback(payload)


def save_markdown_report(markdown_text: str, output_path: str | Path) -> Path:
    """Persist markdown report to disk."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown_text, encoding="utf-8")
    return path
