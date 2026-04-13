"""Deterministic metric display metadata configuration."""

from __future__ import annotations


DEFAULT_DISPLAY = {"value_format": "number", "decimals": 2}

METRIC_DISPLAY = {
    "Perfect Orders": {"value_format": "percentage_ratio", "decimals": 2},
    "Lead Penetration": {"value_format": "number", "decimals": 2},
    "Gross Profit UE": {"value_format": "number", "decimals": 2},
    "Orders": {"value_format": "integer", "decimals": 0},
}


def get_metric_display_config(metric: str) -> dict:
    """Return display config for a metric or a safe default."""
    metric_name = str(metric or "").strip()
    if not metric_name:
        return dict(DEFAULT_DISPLAY)
    return dict(METRIC_DISPLAY.get(metric_name, DEFAULT_DISPLAY))

