"""Assistant-side additive helpers (suggestions + business context awareness)."""

from src.assistant.context_awareness import enrich_question_with_business_context
from src.assistant.suggestions import generate_suggestions

__all__ = [
    "enrich_question_with_business_context",
    "generate_suggestions",
]

