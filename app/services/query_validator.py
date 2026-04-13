"""Intent-aware validation for parsed query payloads."""

from __future__ import annotations

from typing import Any

from app.domain.schemas import (
    AggregationQuery,
    GroupComparisonQuery,
    GrowthAnalysisQuery,
    MultivariableFilterQuery,
    TopNRankingQuery,
    TrendAnalysisQuery,
)


SCHEMA_REGISTRY = {
    "top_n_ranking": TopNRankingQuery,
    "group_comparison": GroupComparisonQuery,
    "trend_analysis": TrendAnalysisQuery,
    "aggregation": AggregationQuery,
    "multivariable_filter": MultivariableFilterQuery,
    "growth_analysis": GrowthAnalysisQuery,
}


def normalize_parsed_payload(payload: dict) -> dict:
    """Apply conservative normalization to common parser deviations before schema validation."""
    payload = dict(payload)

    intent = payload.get("intent")
    filters = dict(payload.get("filters") or {})
    time_scope = dict(payload.get("time_scope") or {})
    params = dict(payload.get("params") or {})
    conditions = payload.get("conditions") or []

    for key in ["country", "city", "zone", "zone_type", "zone_prioritization"]:
        filters.setdefault(key, None)

    time_scope.setdefault("week", 0)
    time_scope.setdefault("last_n_weeks", None)

    for key, value in list(filters.items()):
        if isinstance(value, bool):
            filters[key] = None

    if intent == "top_n_ranking":
        if "top_n" in params and "n" not in params:
            params["n"] = params.pop("top_n")
        params.setdefault("n", 5)
        params.setdefault("order", "desc")
        payload.setdefault("group_by", "zone")
    
    elif intent == "group_comparison":
        params.setdefault("aggregation", "mean")

        group_by = payload.get("group_by")
        filters = payload.get("filters", {})

        if isinstance(group_by, list):
            values = set(group_by)
            if values == {"Wealthy", "Non Wealthy"}:
                payload["group_by"] = "zone_type"
                group_by = "zone_type"

        if isinstance(filters, dict) and isinstance(group_by, str) and group_by in filters:
            filters[group_by] = None

    elif intent == "trend_analysis":
        params.setdefault("aggregation", "mean")
        time_scope["week"] = None

    elif intent == "aggregation":
        params.setdefault("aggregation", "mean")
        group_by = payload.get("group_by")
        if isinstance(filters, dict) and isinstance(group_by, str):
            current_group_filter = filters.get(group_by)
            if current_group_filter is not None:
                next_group_by = {
                    "country": "city",
                    "city": "zone",
                    "zone": "zone_type",
                    "zone_type": "zone_prioritization",
                }.get(group_by)
                if next_group_by:
                    payload["group_by"] = next_group_by
                else:
                    filters[group_by] = None

    elif intent == "multivariable_filter":
        params.setdefault("logical_operator", "and")
        time_scope["last_n_weeks"] = None

    elif intent == "growth_analysis":
        payload["metric"] = "Orders"
        if "explain_growth" in params and "include_driver_analysis" not in params:
            params["include_driver_analysis"] = params.pop("explain_growth")
        params.setdefault("top_k", 5)
        params.setdefault("include_driver_analysis", False)
        time_scope["week"] = None

    payload["filters"] = filters
    payload["time_scope"] = time_scope
    payload["params"] = params
    if conditions:
        payload["conditions"] = conditions

    return payload


def get_schema_for_intent(intent: str):
    """Return schema class for a given intent string."""
    if not intent:
        raise ValueError("Missing 'intent' in parsed payload.")
    schema = SCHEMA_REGISTRY.get(intent)
    if schema is None:
        supported = ", ".join(sorted(SCHEMA_REGISTRY.keys()))
        raise ValueError(f"Unsupported intent '{intent}'. Supported intents: {supported}")
    return schema


def validate_parsed_query(payload: dict[str, Any]):
    """Validate parsed payload against the intent-specific Pydantic model."""
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a dictionary.")
    payload = normalize_parsed_payload(payload)
    intent = payload.get("intent")
    schema = get_schema_for_intent(intent)
    return schema.model_validate(payload)
