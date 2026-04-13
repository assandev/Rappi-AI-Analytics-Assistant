"""Short-term conversation state for follow-up analytics queries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ConversationState:
    """Stores the latest successful request context for follow-up resolution."""

    last_user_question: str | None = None
    last_validated_query: dict[str, Any] | None = None
    last_execution_result: dict[str, Any] | None = None

    def has_previous_query(self) -> bool:
        """Return True when a validated query exists in state."""
        return self.last_validated_query is not None

    def last_validated_query_json(self) -> str | None:
        """Return previous validated query as safe JSON string."""
        if not self.last_validated_query:
            return None
        return json.dumps(self.last_validated_query, ensure_ascii=False, default=str, indent=2)

