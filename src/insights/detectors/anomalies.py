"""Detector for large week-over-week anomalies with executive sanity filters."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

from src.insights.schemas import InsightItem, make_insight


BASE_COLS = ["country", "city", "zone", "metric", "week", "value"]
WOW_PCT_THRESHOLD = 0.10
MIN_BASELINE_ABS = 0.10
MIN_ABS_DELTA = 0.05
SIGN_FLIP_MIN_ABS_DELTA = 0.20


def _prepare_base(metrics_df: pd.DataFrame, orders_df: pd.DataFrame) -> pd.DataFrame:
    metric_part = metrics_df[BASE_COLS].copy()
    orders_part = orders_df[BASE_COLS].copy()
    base = pd.concat([metric_part, orders_part], ignore_index=True)
    base["week"] = pd.to_numeric(base["week"], errors="coerce")
    base["value"] = pd.to_numeric(base["value"], errors="coerce")
    base = base.dropna(subset=["country", "city", "zone", "metric", "week", "value"])
    return base


def _infer_confidence(
    *,
    baseline_abs: float,
    abs_delta: float,
    pct_change_abs: float,
    sign_flip: bool,
) -> str:
    """Infer deterministic confidence level for anomaly credibility."""
    if baseline_abs < 0.3 and pct_change_abs > 2.5:
        return "low"

    score = 0

    if baseline_abs >= 1.0:
        score += 2
    elif baseline_abs >= 0.35:
        score += 1

    if abs_delta >= 0.5:
        score += 2
    elif abs_delta >= 0.2:
        score += 1

    if pct_change_abs >= 0.4:
        score += 2
    elif pct_change_abs >= 0.2:
        score += 1

    if sign_flip:
        score -= 2

    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _metric_specific_hint(metric: str, direction: str) -> str:
    """Return concise deterministic recommendation by metric family."""
    metric_lower = metric.lower()

    if "gross profit" in metric_lower:
        if direction == "deterioration":
            return (
                "Review pricing, discounting, order mix, and variable cost drivers from the last week "
                "to isolate the source of margin deterioration."
            )
        return (
            "Confirm which pricing or cost levers improved margins and test controlled replication in similar zones."
        )

    if "perfect orders" in metric_lower:
        return (
            "Analyze cancellations, delays, and defect incidents in the affected zone and compare "
            "against recent peer performance."
        )

    if "lead penetration" in metric_lower:
        return (
            "Review lead acquisition, merchant activation, and assortment coverage to identify conversion bottlenecks."
        )

    if "adoption" in metric_lower:
        return (
            "Audit availability, demand coverage, and local supply constraints to validate why adoption shifted abruptly."
        )

    if metric_lower == "orders":
        return (
            "Validate demand and supply drivers behind the demand swing before scaling spend or capacity."
        )

    return "Validate the operational drivers of this swing and assign a short-cycle corrective action owner."


def detect_anomalies(
    metrics_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    threshold: float = WOW_PCT_THRESHOLD,
    max_insights: int = 250,
) -> list[InsightItem]:
    """Detect large week-over-week changes between week 1 and week 0 with sanity filtering."""
    base = _prepare_base(metrics_df, orders_df)
    base = base[base["week"].isin([0, 1])]
    if base.empty:
        return []

    grouped = (
        base.groupby(["country", "city", "zone", "metric", "week"], as_index=False)["value"]
        .mean()
        .pivot(index=["country", "city", "zone", "metric"], columns="week", values="value")
        .reset_index()
        .rename(columns={0: "week_0_value", 1: "week_1_value"})
    )

    if "week_0_value" not in grouped.columns or "week_1_value" not in grouped.columns:
        return []

    grouped = grouped.dropna(subset=["week_0_value", "week_1_value"]).copy()
    if grouped.empty:
        return []

    denominator = grouped["week_1_value"].abs()
    grouped["pct_change"] = np.where(
        denominator > 1e-9,
        (grouped["week_0_value"] - grouped["week_1_value"]) / denominator,
        np.nan,
    )
    grouped["abs_delta"] = (grouped["week_0_value"] - grouped["week_1_value"]).abs()
    grouped["baseline_abs"] = grouped["week_1_value"].abs()
    grouped["sign_flip"] = (grouped["week_0_value"] * grouped["week_1_value"]) < 0

    grouped = grouped.dropna(subset=["pct_change"])
    grouped = grouped[grouped["baseline_abs"] >= MIN_BASELINE_ABS]
    grouped = grouped[grouped["abs_delta"] >= MIN_ABS_DELTA]
    grouped = grouped[grouped["pct_change"].abs() >= threshold]

    # Sign flips are volatile; keep only materially large ones.
    grouped = grouped[(~grouped["sign_flip"]) | (grouped["abs_delta"] >= SIGN_FLIP_MIN_ABS_DELTA)]
    if grouped.empty:
        return []

    grouped["confidence"] = grouped.apply(
        lambda row: _infer_confidence(
            baseline_abs=float(row["baseline_abs"]),
            abs_delta=float(row["abs_delta"]),
            pct_change_abs=abs(float(row["pct_change"])),
            sign_flip=bool(row["sign_flip"]),
        ),
        axis=1,
    )

    grouped = grouped[grouped["confidence"].isin(["high", "medium"])].copy()
    if grouped.empty:
        return []

    grouped["severity_score"] = (
        grouped["pct_change"].abs() * 180.0 + grouped["abs_delta"].clip(upper=2.0) * 20.0
    )
    grouped.loc[grouped["sign_flip"], "severity_score"] *= 0.85
    grouped.loc[grouped["confidence"] == "medium", "severity_score"] *= 0.93
    grouped["severity_score"] = grouped["severity_score"].clip(upper=100.0)

    grouped = grouped.sort_values(by=["severity_score", "pct_change"], ascending=[False, False]).head(max_insights)

    insights: list[InsightItem] = []
    for _, row in grouped.iterrows():
        direction = "improvement" if row["pct_change"] > 0 else "deterioration"
        pct_change = float(row["pct_change"])
        week_0_value = float(row["week_0_value"])
        week_1_value = float(row["week_1_value"])
        delta_value = week_0_value - week_1_value
        metric = str(row["metric"])
        country = str(row["country"])
        city = str(row["city"])
        zone = str(row["zone"])
        confidence = str(row["confidence"])
        sign_flip = bool(row["sign_flip"])

        if sign_flip:
            summary = (
                f"{metric} in {zone} ({city}, {country}) shows a {pct_change * 100:.2f}% week-over-week "
                f"{direction} with a sign flip; treat this as high-volatility movement."
            )
        else:
            summary = (
                f"{metric} in {zone} ({city}, {country}) shows a {pct_change * 100:.2f}% "
                f"week-over-week {direction}."
            )

        insights.append(
            cast(
                InsightItem,
                make_insight(
                    category="anomalies",
                    title=f"Large WoW {direction} in {metric}",
                    metric=metric,
                    country=country,
                    city=city,
                    zone=zone,
                    severity_score=float(row["severity_score"]),
                    summary=summary,
                    evidence={
                        "week_1_value": week_1_value,
                        "week_0_value": week_0_value,
                        "pct_change": pct_change,
                        "previous_value": week_1_value,
                        "current_value": week_0_value,
                        "delta_value": delta_value,
                        "wow_change_pct": pct_change,
                        "direction": direction,
                        "baseline_abs": float(row["baseline_abs"]),
                        "abs_delta": float(row["abs_delta"]),
                        "sign_flip": sign_flip,
                        "confidence": confidence,
                        "affected_zones_count": 1,
                    },
                    recommendation_hint=_metric_specific_hint(metric, direction),
                    confidence=cast("high | medium | low", confidence),
                ),
            )
        )

    return insights
