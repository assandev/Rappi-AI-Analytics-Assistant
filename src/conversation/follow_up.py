"""Deterministic follow-up detection and contextual parser input builder."""

from __future__ import annotations

from src.conversation.conversation_state import ConversationState


FOLLOW_UP_MARKERS = (
    "what about",
    "and",
    "same",
    "only",
    "now",
    "also",
)


def is_follow_up_question(question: str) -> bool:
    """Return True when a question looks like a follow-up message."""
    cleaned = question.strip().lower()
    if not cleaned:
        return False

    if any(marker in cleaned for marker in FOLLOW_UP_MARKERS):
        return True

    tokens = cleaned.replace("?", " ").replace(".", " ").split()
    if len(tokens) <= 5 and any(token in {"in", "for", "there", "them", "it"} for token in tokens):
        return True

    return False


def build_contextual_parser_input(question: str, state: ConversationState) -> str:
    """Build contextual parser input for follow-ups, otherwise return raw question."""
    normalized_question = question.strip()
    if not normalized_question:
        return normalized_question

    if not is_follow_up_question(normalized_question):
        return normalized_question

    previous_query_json = state.last_validated_query_json()
    if not previous_query_json:
        return normalized_question

    return (
        "Previous validated query:\n"
        f"{previous_query_json}\n\n"
        "New user follow-up:\n"
        f"{normalized_question}\n\n"
        "Resolve the follow-up using the previous query when appropriate.\n"
        "Preserve prior context unless the new message clearly changes it.\n"
        "If the follow-up adds a filter for the same dimension as group_by, keep the filter and "
        "switch group_by to a compatible lower-granularity dimension.\n"
        "Return exactly one valid JSON object."
    )
