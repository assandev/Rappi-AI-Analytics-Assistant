"""Shared intent enum for chatbot query routing."""

from __future__ import annotations

from enum import Enum


class Intent(str, Enum):
    """Supported structured query intents."""

    TOP_N_RANKING = "top_n_ranking"
    GROUP_COMPARISON = "group_comparison"
    TREND_ANALYSIS = "trend_analysis"
    AGGREGATION = "aggregation"
    MULTIVARIABLE_FILTER = "multivariable_filter"
    GROWTH_ANALYSIS = "growth_analysis"

