"""Pydantic v2 schemas for chatbot query validation."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.intents import Intent


class GroupBy(str, Enum):
    COUNTRY = "country"
    CITY = "city"
    ZONE = "zone"
    ZONE_TYPE = "zone_type"
    ZONE_PRIORITIZATION = "zone_prioritization"


class SortOrder(str, Enum):
    ASC = "asc"
    DESC = "desc"


class AggregationType(str, Enum):
    MEAN = "mean"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    MEDIAN = "median"
    COUNT = "count"


class ConditionOperator(str, Enum):
    HIGH = "high"
    LOW = "low"
    GT = "gt"
    LT = "lt"
    EQ = "eq"


class QueryFilters(BaseModel):
    """Common geography filters."""

    model_config = ConfigDict(extra="forbid")

    country: str | None = None
    city: str | None = None
    zone: str | None = None
    zone_type: str | None = None
    zone_prioritization: str | None = None

    @model_validator(mode="after")
    def normalize_strings(self) -> "QueryFilters":
        for field_name in (
            "country",
            "city",
            "zone",
            "zone_type",
            "zone_prioritization",
        ):
            value = getattr(self, field_name)
            if isinstance(value, str):
                stripped = value.strip()
                setattr(self, field_name, stripped or None)
        return self

    def has_any_filter(self) -> bool:
        return any(
            getattr(self, field_name) is not None
            for field_name in (
                "country",
                "city",
                "zone",
                "zone_type",
                "zone_prioritization",
            )
        )


class TimeScope(BaseModel):
    """Common time scope fields."""

    model_config = ConfigDict(extra="forbid")

    week: int | None = 0
    last_n_weeks: int | None = None

    @field_validator("week")
    @classmethod
    def validate_week(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if value < 0 or value > 8:
            raise ValueError("week must be between 0 and 8.")
        return value


class TopNParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n: int = Field(default=5, ge=1, le=50)
    order: SortOrder = SortOrder.DESC


class ComparisonParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aggregation: str = "mean"

    @field_validator("aggregation")
    @classmethod
    def validate_aggregation(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {agg.value for agg in AggregationType}
        if normalized not in allowed:
            raise ValueError(f"aggregation must be one of: {sorted(allowed)}")
        return normalized


class TrendParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aggregation: str = "mean"

    @field_validator("aggregation")
    @classmethod
    def validate_aggregation(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {agg.value for agg in AggregationType}
        if normalized not in allowed:
            raise ValueError(f"aggregation must be one of: {sorted(allowed)}")
        return normalized


class AggregationParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aggregation: AggregationType = AggregationType.MEAN


class MetricCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    operator: ConditionOperator
    value: float | None = None

    @field_validator("metric")
    @classmethod
    def validate_metric(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("metric must not be blank.")
        return normalized

    @model_validator(mode="after")
    def validate_operator_value_pair(self) -> "MetricCondition":
        numeric_ops = {ConditionOperator.GT, ConditionOperator.LT, ConditionOperator.EQ}
        rank_ops = {ConditionOperator.HIGH, ConditionOperator.LOW}

        if self.operator in numeric_ops and self.value is None:
            raise ValueError("value is required when operator is gt, lt, or eq.")
        if self.operator in rank_ops and self.value is not None:
            raise ValueError("value must be omitted when operator is high or low.")
        return self


class MultivariableParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    logical_operator: Literal["and", "or"] = "and"


class GrowthAnalysisParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k: int = Field(default=5, ge=1, le=50)
    include_driver_analysis: bool = False


class BaseIntentQuery(BaseModel):
    """Shared strict config for all intent models."""

    model_config = ConfigDict(extra="forbid")


class TopNRankingQuery(BaseIntentQuery):
    intent: Literal[Intent.TOP_N_RANKING] = Intent.TOP_N_RANKING
    metric: str
    filters: QueryFilters = Field(default_factory=QueryFilters)
    time_scope: TimeScope = Field(default_factory=TimeScope)
    group_by: GroupBy = GroupBy.ZONE
    params: TopNParams = Field(default_factory=TopNParams)

    @model_validator(mode="after")
    def validate_top_n_constraints(self) -> "TopNRankingQuery":
        if self.time_scope.last_n_weeks is not None:
            raise ValueError("last_n_weeks is not allowed for top_n_ranking.")
        return self


class GroupComparisonQuery(BaseIntentQuery):
    intent: Literal[Intent.GROUP_COMPARISON] = Intent.GROUP_COMPARISON
    metric: str
    filters: QueryFilters = Field(default_factory=QueryFilters)
    time_scope: TimeScope = Field(default_factory=TimeScope)
    group_by: GroupBy
    params: ComparisonParams = Field(default_factory=ComparisonParams)

    @model_validator(mode="after")
    def validate_group_comparison_constraints(self) -> "GroupComparisonQuery":
        if self.time_scope.last_n_weeks is not None:
            raise ValueError("last_n_weeks is not allowed for group_comparison.")
        if getattr(self.filters, self.group_by.value) is not None:
            raise ValueError("group_by cannot also be fixed in filters.")
        return self


class TrendAnalysisQuery(BaseIntentQuery):
    intent: Literal[Intent.TREND_ANALYSIS] = Intent.TREND_ANALYSIS
    metric: str
    filters: QueryFilters = Field(default_factory=QueryFilters)
    time_scope: TimeScope = Field(default_factory=TimeScope)
    params: TrendParams = Field(default_factory=TrendParams)

    @model_validator(mode="after")
    def validate_trend_constraints(self) -> "TrendAnalysisQuery":
        if self.time_scope.last_n_weeks is None:
            raise ValueError("last_n_weeks is required for trend_analysis.")
        if self.time_scope.last_n_weeks < 2 or self.time_scope.last_n_weeks > 9:
            raise ValueError("last_n_weeks must be between 2 and 9 for trend_analysis.")
        if not self.filters.has_any_filter():
            raise ValueError("At least one filter must be provided for trend_analysis.")
        return self


class AggregationQuery(BaseIntentQuery):
    intent: Literal[Intent.AGGREGATION] = Intent.AGGREGATION
    metric: str
    filters: QueryFilters = Field(default_factory=QueryFilters)
    time_scope: TimeScope = Field(default_factory=TimeScope)
    group_by: GroupBy
    params: AggregationParams = Field(default_factory=AggregationParams)

    @model_validator(mode="after")
    def validate_aggregation_constraints(self) -> "AggregationQuery":
        if self.time_scope.last_n_weeks is not None:
            raise ValueError("last_n_weeks is not allowed for aggregation.")
        if getattr(self.filters, self.group_by.value) is not None:
            raise ValueError("group_by cannot also be fixed in filters.")
        return self


class MultivariableFilterQuery(BaseIntentQuery):
    intent: Literal[Intent.MULTIVARIABLE_FILTER] = Intent.MULTIVARIABLE_FILTER
    filters: QueryFilters = Field(default_factory=QueryFilters)
    time_scope: TimeScope = Field(default_factory=TimeScope)
    conditions: list[MetricCondition]
    params: MultivariableParams = Field(default_factory=MultivariableParams)

    @model_validator(mode="after")
    def validate_multivariable_constraints(self) -> "MultivariableFilterQuery":
        if self.time_scope.last_n_weeks is not None:
            raise ValueError("last_n_weeks is not allowed for multivariable_filter.")
        if len(self.conditions) < 2:
            raise ValueError("At least 2 conditions are required for multivariable_filter.")

        metrics = [condition.metric.lower() for condition in self.conditions]
        if len(set(metrics)) != len(metrics):
            raise ValueError("All condition metrics must be different.")
        return self


class GrowthAnalysisQuery(BaseIntentQuery):
    intent: Literal[Intent.GROWTH_ANALYSIS] = Intent.GROWTH_ANALYSIS
    metric: str = "Orders"
    filters: QueryFilters = Field(default_factory=QueryFilters)
    time_scope: TimeScope = Field(default_factory=TimeScope)
    params: GrowthAnalysisParams = Field(default_factory=GrowthAnalysisParams)

    @field_validator("metric")
    @classmethod
    def validate_growth_metric(cls, value: str) -> str:
        if value.strip().lower() != "orders":
            raise ValueError("Only metric='Orders' is allowed for growth_analysis in MVP.")
        return "Orders"

    @model_validator(mode="after")
    def validate_growth_constraints(self) -> "GrowthAnalysisQuery":
        if self.time_scope.last_n_weeks is None:
            raise ValueError("last_n_weeks is required for growth_analysis.")
        if self.time_scope.last_n_weeks < 2 or self.time_scope.last_n_weeks > 9:
            raise ValueError("last_n_weeks must be between 2 and 9 for growth_analysis.")
        if self.time_scope.week is not None:
            raise ValueError("week must be None for growth_analysis.")
        return self


AnyIntentQuery = (
    TopNRankingQuery
    | GroupComparisonQuery
    | TrendAnalysisQuery
    | AggregationQuery
    | MultivariableFilterQuery
    | GrowthAnalysisQuery
)


# Example usages:
# top_n = TopNRankingQuery(metric="Gross Profit UE")
# group_cmp = GroupComparisonQuery(metric="Turbo Adoption", group_by=GroupBy.CITY)
# trend = TrendAnalysisQuery(
#     metric="Perfect Orders",
#     filters=QueryFilters(country="CO"),
#     time_scope=TimeScope(week=None, last_n_weeks=6),
# )
# agg = AggregationQuery(metric="Lead Penetration", group_by=GroupBy.ZONE_TYPE)
# multif = MultivariableFilterQuery(
#     conditions=[
#         MetricCondition(metric="Perfect Orders", operator=ConditionOperator.GT, value=0.8),
#         MetricCondition(metric="Lead Penetration", operator=ConditionOperator.LOW),
#     ]
# )
# growth = GrowthAnalysisQuery(
#     metric="Orders",
#     time_scope=TimeScope(week=None, last_n_weeks=8),
# )

