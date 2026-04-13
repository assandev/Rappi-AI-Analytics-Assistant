"""LLM-assisted executive markdown report generation from deterministic insights."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from src.insights.schemas import InsightPayload


CATEGORY_TITLES: list[tuple[str, str]] = [
    ("anomalies", "Anomalies"),
    ("trends", "Concerning Trends"),
    ("benchmarking", "Benchmarking"),
    ("correlations", "Correlations"),
    ("opportunities", "Opportunities"),
]

CATEGORY_MATTERS_TEMPLATES: dict[str, str] = {
    "anomalies": "This signals abrupt operational change that may require immediate triage or replication.",
    "trends": "Sustained movement over multiple weeks can impact service consistency and near-term outcomes.",
    "benchmarking": "Peer divergence highlights where performance is lagging or where best practices can be replicated.",
    "correlations": "This relationship can help prioritize coordinated actions across connected metrics.",
    "opportunities": "This points to concrete upside if resources are focused on the identified zone pattern.",
}

CATEGORY_ACTION_FALLBACKS: dict[str, str] = {
    "anomalies": "Run a rapid zone-level review and define corrective or replication actions this week.",
    "trends": "Assign an owner to monitor this trend weekly and execute a targeted stabilization plan.",
    "benchmarking": "Compare process differences versus peers and roll out the top actionable practice.",
    "correlations": "Use this relationship to prioritize interventions on the leading operational lever.",
    "opportunities": "Pilot a focused action plan in high-potential zones and track impact over the next cycle.",
}

REQUIRED_SECTIONS = [
    "# Weekly Executive Insights Report",
    "## Executive Summary",
    "## Key Insights by Category",
    "## Cross-Cutting Recommendations",
]


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _format_number(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return _safe_text(value)

    if numeric.is_integer():
        return str(int(numeric))
    return f"{numeric:.4f}".rstrip("0").rstrip(".")


def _to_sentence_case(value: str) -> str:
    raw = value.replace("_", " ").strip()
    if not raw:
        return ""
    return raw[0].upper() + raw[1:]


def _location_text(insight: dict[str, Any]) -> str:
    parts = [
        _safe_text(insight.get("country")),
        _safe_text(insight.get("city")),
        _safe_text(insight.get("zone")),
    ]
    parts = [part for part in parts if part]
    if not parts:
        return ""
    return " | ".join(parts)


def _format_evidence_lines(evidence: dict[str, Any], max_lines: int = 4) -> list[str]:
    lines: list[str] = []
    for key in sorted(evidence.keys()):
        value = evidence[key]
        key_text = _to_sentence_case(str(key))
        if isinstance(value, list):
            value_text = ", ".join(_format_number(item) for item in value)
        elif isinstance(value, dict):
            compact = ", ".join(f"{k}: {_format_number(v)}" for k, v in sorted(value.items()))
            value_text = compact
        else:
            value_text = _format_number(value)
        lines.append(f"{key_text}: {value_text}")
        if len(lines) >= max_lines:
            break
    return lines


def _prepare_insight_block(insight: dict[str, Any]) -> dict[str, Any]:
    category = _safe_text(insight.get("category"))
    metric = _safe_text(insight.get("metric"))
    summary = _safe_text(insight.get("summary"))
    location = _location_text(insight)

    happened = summary
    if location and metric:
        happened = f"{summary} Location: {location}. Metric: {metric}."
    elif location:
        happened = f"{summary} Location: {location}."
    elif metric:
        happened = f"{summary} Metric: {metric}."

    why_it_matters = CATEGORY_MATTERS_TEMPLATES.get(
        category,
        "This finding may affect operational performance and should be reviewed with ownership.",
    )

    evidence = insight.get("evidence")
    evidence_lines = _format_evidence_lines(evidence if isinstance(evidence, dict) else {})
    if not evidence_lines:
        evidence_lines = ["No additional structured evidence was provided."]

    recommendation_hint = _safe_text(insight.get("recommendation_hint"))
    recommended_action = recommendation_hint or CATEGORY_ACTION_FALLBACKS.get(
        category,
        "Review this finding with the responsible team and define the next concrete action.",
    )

    return {
        "title": _safe_text(insight.get("title")) or "Untitled insight",
        "category": category,
        "metric": metric,
        "what_happened": happened,
        "why_it_matters": why_it_matters,
        "evidence_lines": evidence_lines,
        "recommended_action": recommended_action,
    }


def prepare_executive_summary_insights(payload: InsightPayload, max_items: int = 5) -> list[dict[str, Any]]:
    """Prepare compact executive-summary insights for report generation."""
    items = payload.get("executive_summary_insights", [])[:max_items]
    return [_prepare_insight_block(item) for item in items]


def prepare_category_sections(payload: InsightPayload, max_per_category: int = 3) -> dict[str, list[dict[str, Any]]]:
    """Prepare category sections in presentation-friendly structure."""
    grouped = payload.get("insights_by_category", {})
    sections: dict[str, list[dict[str, Any]]] = {}

    for key, title in CATEGORY_TITLES:
        raw_items = grouped.get(key, [])[:max_per_category]
        sections[title] = [_prepare_insight_block(item) for item in raw_items]

    return sections


def build_cross_cutting_recommendations(payload: InsightPayload, max_items: int = 6) -> list[str]:
    """Build deduplicated, concise cross-cutting recommendations."""
    seen: set[str] = set()
    recommendations: list[str] = []

    ranked_source: list[dict[str, Any]] = []
    ranked_source.extend(payload.get("executive_summary_insights", []))
    for _, items in payload.get("insights_by_category", {}).items():
        ranked_source.extend(items)

    for insight in ranked_source:
        recommendation = _safe_text(insight.get("recommendation_hint"))
        if not recommendation:
            category = _safe_text(insight.get("category"))
            recommendation = CATEGORY_ACTION_FALLBACKS.get(category, "Review and prioritize a concrete owner action.")
        if recommendation in seen:
            continue
        seen.add(recommendation)
        recommendations.append(recommendation)
        if len(recommendations) >= max_items:
            break

    return recommendations


def _prepare_report_payload(payload: InsightPayload) -> dict[str, Any]:
    """Shape deterministic payload into executive report-ready structure."""
    return {
        "generated_at": payload.get("generated_at"),
        "insight_count": payload.get("insight_count", 0),
        "curation_metadata": payload.get("curation_metadata", {}),
        "executive_summary_insights": prepare_executive_summary_insights(payload, max_items=5),
        "category_sections": prepare_category_sections(payload, max_per_category=3),
        "cross_cutting_recommendations": build_cross_cutting_recommendations(payload, max_items=6),
    }


def build_report_system_prompt() -> str:
    """Build strict executive-report prompt with no-invention rules."""
    return (
        "You are an executive operations analytics report writer.\n"
        "Write concise, decision-oriented weekly insight memos for business stakeholders.\n\n"
        "Hard rules:\n"
        "- Use only facts provided in the input payload.\n"
        "- Do not invent findings, metrics, values, geographies, causes, or recommendations unrelated to findings.\n"
        "- Do not expose raw internal metadata such as severity_score or priority_score in the report body.\n"
        "- Keep language executive, clear, and actionable.\n"
        "- Output valid Markdown only.\n\n"
        "Required structure (exact headings):\n"
        "# Weekly Executive Insights Report\n"
        "## Executive Summary\n"
        "## Key Insights by Category\n"
        "### Anomalies\n"
        "### Concerning Trends\n"
        "### Benchmarking\n"
        "### Correlations\n"
        "### Opportunities\n"
        "## Cross-Cutting Recommendations\n\n"
        "For each insight under categories use:\n"
        "#### [Insight title]\n"
        "**What happened:** ...\n"
        "**Why it matters:** ...\n"
        "**Evidence:** ...\n"
        "**Recommended action:** ...\n"
    )


def build_report_user_prompt(payload: InsightPayload) -> str:
    """Build user prompt with prepared executive-friendly payload."""
    prepared = _prepare_report_payload(payload)
    prepared_json = json.dumps(prepared, ensure_ascii=False, indent=2, default=str)

    return (
        "Create the weekly executive insights report in Markdown.\n"
        "Use only the provided prepared payload.\n"
        "Do not add facts not present in input.\n"
        "If a category has no insights, write: 'No material findings this week.'\n\n"
        "Prepared payload:\n"
        f"{prepared_json}"
    )


def _render_insight_block(lines: list[str], insight: dict[str, Any]) -> None:
    lines.append(f"#### {insight['title']}")
    lines.append(f"**What happened:** {insight['what_happened']}")
    lines.append(f"**Why it matters:** {insight['why_it_matters']}")

    evidence_lines = insight.get("evidence_lines", [])
    if evidence_lines:
        lines.append("**Evidence:**")
        for evidence in evidence_lines:
            lines.append(f"- {evidence}")
    else:
        lines.append("**Evidence:** No additional structured evidence was provided.")

    lines.append(f"**Recommended action:** {insight['recommended_action']}")
    lines.append("")


def build_markdown_fallback(payload: InsightPayload) -> str:
    """Deterministic executive fallback when LLM is unavailable or invalid."""
    prepared = _prepare_report_payload(payload)

    lines: list[str] = []
    lines.append("# Weekly Executive Insights Report")
    lines.append("")

    lines.append("## Executive Summary")
    summary_items = prepared["executive_summary_insights"]
    if summary_items:
        for item in summary_items[:5]:
            lines.append(f"- **{item['title']}**: {item['what_happened']}")
    else:
        lines.append("- No material findings this week.")
    lines.append("")

    lines.append("## Key Insights by Category")
    category_sections = prepared["category_sections"]
    for _, title in CATEGORY_TITLES:
        lines.append("")
        lines.append(f"### {title}")
        insights = category_sections.get(title, [])
        if not insights:
            lines.append("No material findings this week.")
            continue
        for insight in insights:
            _render_insight_block(lines, insight)

    lines.append("## Cross-Cutting Recommendations")
    recommendations = prepared["cross_cutting_recommendations"]
    if recommendations:
        for recommendation in recommendations:
            lines.append(f"- {recommendation}")
    else:
        lines.append("- No cross-cutting actions were identified this week.")

    return "\n".join(lines).strip() + "\n"


def _looks_like_markdown(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("#")


def _has_required_structure(text: str) -> bool:
    normalized = text.strip()
    return all(section in normalized for section in REQUIRED_SECTIONS)


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
        if not _has_required_structure(markdown_text):
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
