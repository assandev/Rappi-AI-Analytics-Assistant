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

REQUIRED_SECTIONS = [
    "# Weekly Executive Insights Report",
    "## Executive Summary",
    "## Key Insights by Category",
    "### Anomalies",
    "### Concerning Trends",
    "### Benchmarking",
    "### Correlations",
    "### Opportunities",
    "## Cross-Cutting Recommendations",
]


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _format_number(value: Any, decimals: int = 4) -> str:
    number = _to_float(value)
    if number is None:
        return _safe_text(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.{decimals}f}".rstrip("0").rstrip(".")


def _format_pct_ratio(value: Any, decimals: int = 2) -> str:
    number = _to_float(value)
    if number is None:
        return _safe_text(value)
    return f"{number * 100:.{decimals}f}%"


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


def _metric_family(metric: str) -> str:
    metric_lower = metric.lower()
    if "gross profit" in metric_lower:
        return "margin"
    if "perfect orders" in metric_lower:
        return "quality"
    if "lead penetration" in metric_lower:
        return "penetration"
    if "adoption" in metric_lower:
        return "adoption"
    if "markdown" in metric_lower:
        return "cost_pressure"
    if metric_lower == "orders" or ("orders" in metric_lower and "perfect orders" not in metric_lower):
        return "demand"
    return "general"


def _infer_direction(category: str, evidence: dict[str, Any], summary: str) -> str:
    explicit = _safe_text(evidence.get("direction"))
    if explicit:
        return explicit

    if category == "benchmarking":
        gap = _to_float(evidence.get("gap_pct"))
        if gap is not None:
            return "outperformance" if gap > 0 else "underperformance"

    if category == "correlations":
        corr = _to_float(evidence.get("correlation"))
        if corr is not None:
            return "positive" if corr > 0 else "negative"

    summary_lower = summary.lower()
    if "deteriorat" in summary_lower or "declin" in summary_lower:
        return "deterioration"
    if "improv" in summary_lower or "growth" in summary_lower:
        return "improvement"

    return "change"


def _build_why_it_matters(category: str, metric_family: str, direction: str, evidence: dict[str, Any]) -> str:
    if category == "anomalies":
        sign_flip = bool(evidence.get("sign_flip", False))
        if metric_family == "margin" and direction == "deterioration":
            text = "This may indicate a sudden margin disruption that could affect profitability in the zone."
        elif metric_family == "quality" and direction == "deterioration":
            text = "This suggests a sudden operational quality issue that may affect user experience and retention."
        elif metric_family in {"adoption", "penetration", "demand"} and direction == "deterioration":
            text = "This may reflect weakening demand, availability, or coverage problems in the zone."
        elif direction == "improvement":
            text = "This may reveal a high-impact operating change worth validating and replicating in similar zones."
        else:
            text = "This abrupt movement may materially affect short-term operating outcomes and requires validation."
        if sign_flip:
            text += " The sign flip suggests higher volatility, so confirm persistence before scaling decisions."
        return text

    if category == "trends":
        if metric_family == "quality":
            return "This sustained decline suggests a structural service-quality issue rather than a one-week fluctuation."
        if metric_family == "margin":
            return "This sustained deterioration suggests structural profitability pressure that may persist without intervention."
        return "This sustained decline suggests a structural issue rather than a one-week fluctuation."

    if category == "benchmarking":
        if direction == "underperformance":
            return "This peer gap suggests meaningful local operating gaps versus comparable zones and likely upside from targeted fixes."
        if direction == "outperformance":
            return "This peer gap suggests a potentially replicable operating advantage that can inform broader rollout."
        return "This peer divergence highlights meaningful performance differences versus comparable zones."

    if category == "correlations":
        if direction == "negative":
            return "This inverse relationship suggests a potential trade-off, so interventions should track both metrics together."
        return "This relationship suggests these metrics should be monitored together when designing interventions."

    if category == "opportunities":
        if metric_family in {"demand", "penetration"}:
            return "This indicates growth upside, but execution safeguards are needed before scaling further."
        return "This indicates actionable upside if the identified zone pattern is converted into a focused operating plan."

    return "This finding has direct operational relevance and should be incorporated into near-term decisions."


def _build_recommended_action(
    category: str,
    metric_family: str,
    direction: str,
    evidence: dict[str, Any],
    recommendation_hint: str,
    title: str,
) -> str:
    title_lower = title.lower()

    if category == "anomalies":
        if metric_family == "margin":
            if direction == "improvement":
                return (
                    "Validate which pricing, mix, or cost levers drove this margin uplift and test controlled "
                    "replication in comparable zones."
                )
            return (
                "Review pricing, discounting, order mix, and cost drivers in the last week to identify the source "
                "of margin deterioration."
            )
        if metric_family == "quality":
            if direction == "improvement":
                return "Confirm which operational fixes improved quality and standardize them in similar zones."
            return (
                "Analyze cancellations, delays, and defect incidents in the affected zone and compare them against "
                "recent peer performance."
            )
        if metric_family == "penetration":
            return (
                "Review lead acquisition, merchant activation, and local assortment coverage to identify conversion "
                "bottlenecks."
            )
        if metric_family == "adoption":
            return "Audit local supply and availability levers to recover adoption before expanding demand efforts."
        if metric_family == "demand":
            return "Validate demand and capacity signals before scaling spend or inventory commitments."

    if category == "trends":
        if metric_family == "quality":
            return "Create a 2-week quality recovery plan with daily defect tracking and zone-level owner accountability."
        if metric_family == "margin":
            return "Run a margin recovery review on pricing, mix, and costs, then implement the top two corrective levers."
        return "Assign an owner and launch a short-cycle corrective plan with weekly checkpoint reviews."

    if category == "benchmarking":
        if direction == "underperformance":
            return (
                "Compare local operating practices with top-performing peer zones and test replication of the strongest levers."
            )
        return "Document this outperforming playbook and pilot replication in comparable underperforming zones."

    if category == "correlations":
        return (
            "Track both metrics together and design coordinated interventions rather than optimizing them in isolation."
        )

    if category == "opportunities":
        if "quality risk" in title_lower:
            return "Protect growth by prioritizing quality safeguards before scaling demand further in this zone."
        if "low penetration" in title_lower:
            return (
                "Run targeted acquisition and assortment actions to convert quality strength into higher penetration."
            )
        if "replication" in title_lower:
            return (
                "Codify the local operating playbook and run a controlled replication pilot in similar peer zones."
            )
        return "Prioritize this opportunity in the next planning cycle with a clear owner, target, and review cadence."

    if recommendation_hint:
        return recommendation_hint
    return "Review this finding with the responsible team and define one concrete next action this week."


def _format_anomaly_evidence(evidence: dict[str, Any]) -> list[str]:
    previous = evidence.get("previous_value", evidence.get("week_1_value"))
    current = evidence.get("current_value", evidence.get("week_0_value"))
    wow = evidence.get("wow_change_pct", evidence.get("pct_change"))
    abs_delta = evidence.get("abs_delta", evidence.get("delta_value"))
    confidence = _safe_text(evidence.get("confidence"))

    lines = [
        f"Previous value: {_format_number(previous)}",
        f"Current value: {_format_number(current)}",
        f"Week-over-week change: {_format_pct_ratio(wow)}",
        f"Absolute change: {_format_number(abs_delta)}",
    ]
    if confidence:
        lines.append(f"Confidence: {confidence.title()}")
    if bool(evidence.get("sign_flip", False)):
        lines.append("Sign stability: Value crossed zero (high volatility)")
    return lines


def _format_trend_evidence(evidence: dict[str, Any]) -> list[str]:
    net_change = evidence.get("net_change_pct")
    lines = [
        f"Deterioration streak: {_format_number(evidence.get('run_length'))} weeks",
        f"Start point: Week {_format_number(evidence.get('start_week'))} at {_format_number(evidence.get('start_value'))}",
        f"End point: Week {_format_number(evidence.get('end_week'))} at {_format_number(evidence.get('end_value'))}",
    ]
    if net_change is not None:
        lines.append(f"Net change over streak: {_format_pct_ratio(net_change)}")
    return lines


def _format_benchmarking_evidence(evidence: dict[str, Any]) -> list[str]:
    return [
        f"Zone value: {_format_number(evidence.get('zone_value'))}",
        f"Peer average: {_format_number(evidence.get('peer_mean'))}",
        f"Peer gap vs average: {_format_pct_ratio(evidence.get('gap_pct'))}",
        f"Peer sample size: {_format_number(evidence.get('peer_count'))}",
    ]


def _format_correlation_evidence(evidence: dict[str, Any]) -> list[str]:
    corr = _to_float(evidence.get("correlation"))
    direction = "positive" if (corr is not None and corr > 0) else "negative"
    return [
        f"Metric pair: {_safe_text(evidence.get('metric_x'))} and {_safe_text(evidence.get('metric_y'))}",
        f"Correlation strength: r={_format_number(corr, decimals=2)} ({direction})",
        f"Sample size: {_format_number(evidence.get('sample_size'))} zones",
    ]


def _format_opportunity_evidence(evidence: dict[str, Any]) -> list[str]:
    key_mapping = [
        ("orders_growth_pct", "Orders growth (week 3 to week 0)", "pct"),
        ("perfect_orders", "Perfect Orders", "num"),
        ("country_perfect_orders_median", "Country median Perfect Orders", "num"),
        ("lead_penetration", "Lead Penetration", "num"),
        ("country_quality_p75", "Country P75 Perfect Orders", "num"),
        ("country_penetration_p25", "Country P25 Lead Penetration", "num"),
        ("gross_profit_ue", "Gross Profit UE", "num"),
        ("country_gp_top_decile", "Country top decile Gross Profit UE", "num"),
        ("turbo_adoption", "Turbo Adoption", "num"),
        ("country_turbo_median", "Country median Turbo Adoption", "num"),
    ]

    lines: list[str] = []
    for key, label, value_type in key_mapping:
        if key not in evidence:
            continue
        if value_type == "pct":
            lines.append(f"{label}: {_format_pct_ratio(evidence.get(key))}")
        else:
            lines.append(f"{label}: {_format_number(evidence.get(key))}")
        if len(lines) >= 4:
            break

    if not lines:
        lines.append("Evidence: Opportunity signal detected from deterministic threshold checks.")
    return lines


def _format_evidence_lines(category: str, evidence: dict[str, Any]) -> list[str]:
    if category == "anomalies":
        return _format_anomaly_evidence(evidence)
    if category == "trends":
        return _format_trend_evidence(evidence)
    if category == "benchmarking":
        return _format_benchmarking_evidence(evidence)
    if category == "correlations":
        return _format_correlation_evidence(evidence)
    if category == "opportunities":
        return _format_opportunity_evidence(evidence)

    lines: list[str] = []
    for key in sorted(evidence.keys()):
        lines.append(f"{key.replace('_', ' ').title()}: {_format_number(evidence[key])}")
        if len(lines) >= 4:
            break
    return lines


def _prepare_insight_block(insight: dict[str, Any]) -> dict[str, Any]:
    category = _safe_text(insight.get("category"))
    metric = _safe_text(insight.get("metric"))
    summary = _safe_text(insight.get("summary"))
    title = _safe_text(insight.get("title")) or "Untitled insight"
    location = _location_text(insight)
    recommendation_hint = _safe_text(insight.get("recommendation_hint"))
    evidence = insight.get("evidence") if isinstance(insight.get("evidence"), dict) else {}

    happened = summary
    if location and metric:
        happened = f"{summary} Location: {location}. Metric: {metric}."
    elif location:
        happened = f"{summary} Location: {location}."
    elif metric:
        happened = f"{summary} Metric: {metric}."

    direction = _infer_direction(category, evidence, summary)
    metric_family = _metric_family(metric)

    why_it_matters = _build_why_it_matters(category, metric_family, direction, evidence)
    recommended_action = _build_recommended_action(
        category=category,
        metric_family=metric_family,
        direction=direction,
        evidence=evidence,
        recommendation_hint=recommendation_hint,
        title=title,
    )

    evidence_lines = _format_evidence_lines(category, evidence)
    if not evidence_lines:
        evidence_lines = ["No additional structured evidence was provided."]

    return {
        "title": title,
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
    """Build deduplicated cross-cutting recommendations from prepared deterministic actions."""
    seen: set[str] = set()
    recommendations: list[str] = []

    ranked_source: list[dict[str, Any]] = []
    ranked_source.extend(payload.get("executive_summary_insights", []))
    for _, items in payload.get("insights_by_category", {}).items():
        ranked_source.extend(items)

    for insight in ranked_source:
        block = _prepare_insight_block(insight)
        recommendation = _safe_text(block["recommended_action"])
        if not recommendation or recommendation in seen:
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
        "Write concise, action-oriented weekly memos for business stakeholders.\n\n"
        "Hard rules:\n"
        "- Use only facts provided in the prepared payload.\n"
        "- Do not invent findings, metrics, values, geographies, causes, or recommendations.\n"
        "- Keep recommendations tied to evidence in the payload.\n"
        "- Do not expose internal metadata fields like severity_score or priority_score.\n"
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
        "For each insight in category sections use:\n"
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
        "Use only the prepared payload below.\n"
        "Do not add facts not present in input.\n"
        "If a category has no findings, write: 'No material findings this week.'\n"
        "Keep wording concise and business-facing.\n\n"
        "Prepared payload:\n"
        f"{prepared_json}"
    )


def _render_insight_block(lines: list[str], insight: dict[str, Any]) -> None:
    lines.append(f"#### {insight['title']}")
    lines.append(f"**What happened:** {insight['what_happened']}")
    lines.append(f"**Why it matters:** {insight['why_it_matters']}")

    lines.append("**Evidence:**")
    for evidence in insight.get("evidence_lines", []):
        lines.append(f"- {evidence}")

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
