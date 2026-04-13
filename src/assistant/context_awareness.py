"""Deterministic business-term awareness to enrich parser input."""

from __future__ import annotations

import unicodedata


BUSINESS_CONTEXT_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        (
            "problematic zones",
            "zones with issues",
            "problem zones",
            "zonas problematicas",
            "zonas con problemas",
            "zonas con issues",
        ),
        "Which zones have low Perfect Orders or low Gross Profit UE this week?",
    ),
    (
        (
            "underperforming zones",
            "low performing zones",
            "zonas de bajo rendimiento",
            "zonas con bajo rendimiento",
        ),
        "Which zones have below average performance in key metrics like Perfect Orders or Gross Profit UE?",
    ),
    (
        (
            "top performing zones",
            "high performing zones",
            "best performing zones",
            "zonas de alto rendimiento",
            "zonas de mejor rendimiento",
        ),
        "Which zones have the highest Perfect Orders and Gross Profit UE this week?",
    ),
    (
        (
            "fast growing zones",
            "fastest growing zones",
            "high growth zones",
            "zonas de rapido crecimiento",
            "zonas que crecen rapido",
        ),
        "Which zones are growing fastest in orders over the last weeks?",
    ),
    (
        (
            "zones with quality issues",
            "quality issue zones",
            "zonas con problemas de calidad",
            "zonas con issues de calidad",
        ),
        "Which zones have low Perfect Orders this week?",
    ),
]


def _normalize_for_match(text: str) -> str:
    """Lowercase and remove accents for stable keyword matching."""
    cleaned = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(cleaned.lower().strip().split())


def enrich_question_with_business_context(question: str) -> str:
    """Append explicit business clarification when known shorthand terms are used."""
    if not isinstance(question, str):
        return question

    original_question = question.strip()
    if not original_question:
        return original_question

    normalized_question = _normalize_for_match(original_question)
    if "clarification:" in normalized_question:
        return original_question

    for keywords, clarification in BUSINESS_CONTEXT_RULES:
        if any(keyword in normalized_question for keyword in keywords):
            return f"{original_question} Clarification: {clarification}"

    return original_question

