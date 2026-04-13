"""Detector for actionable opportunity insights."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

from src.insights.schemas import InsightItem, make_insight


def _prepare_metrics_snapshot(metrics_df: pd.DataFrame) -> pd.DataFrame:
    cols = ["country", "city", "zone", "zone_type", "metric", "week", "value"]
    data = metrics_df[cols].copy()
    data["week"] = pd.to_numeric(data["week"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data = data.dropna(subset=["country", "city", "zone", "metric", "week", "value"])
    data = data[data["week"] == 0].copy()
    if data.empty:
        return data
    return (
        data.groupby(["country", "city", "zone", "zone_type", "metric"], as_index=False)["value"]
        .mean()
        .reset_index(drop=True)
    )


def _prepare_orders_growth(orders_df: pd.DataFrame) -> pd.DataFrame:
    cols = ["country", "city", "zone", "metric", "week", "value"]
    data = orders_df[cols].copy()
    data["week"] = pd.to_numeric(data["week"], errors="coerce")
    data["value"] = pd.to_numeric(data["value"], errors="coerce")
    data = data.dropna(subset=["country", "city", "zone", "week", "value"])
    data = data[data["week"].isin([0, 3])].copy()
    if data.empty:
        return data

    pivot = (
        data.groupby(["country", "city", "zone", "week"], as_index=False)["value"]
        .mean()
        .pivot(index=["country", "city", "zone"], columns="week", values="value")
        .reset_index()
        .rename(columns={0: "orders_week_0", 3: "orders_week_3"})
    )
    if "orders_week_0" not in pivot.columns or "orders_week_3" not in pivot.columns:
        return pd.DataFrame(columns=["country", "city", "zone", "orders_week_0", "orders_week_3", "orders_growth_pct"])

    pivot = pivot.dropna(subset=["orders_week_0", "orders_week_3"]).copy()
    if pivot.empty:
        return pivot

    den = pivot["orders_week_3"].abs()
    pivot["orders_growth_pct"] = np.where(
        den > 1e-9,
        (pivot["orders_week_0"] - pivot["orders_week_3"]) / den,
        np.nan,
    )
    return pivot.dropna(subset=["orders_growth_pct"])


def _wide_metrics(snapshot: pd.DataFrame, metrics: list[str]) -> pd.DataFrame:
    wide = snapshot[snapshot["metric"].isin(metrics)].pivot_table(
        index=["country", "city", "zone", "zone_type"], columns="metric", values="value", aggfunc="mean"
    )
    return wide.reset_index() if not wide.empty else pd.DataFrame()


def detect_opportunities(
    metrics_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    max_insights: int = 250,
) -> list[InsightItem]:
    """Detect straightforward action opportunities from deterministic heuristics."""
    snapshot = _prepare_metrics_snapshot(metrics_df)
    orders_growth = _prepare_orders_growth(orders_df)
    insights: list[InsightItem] = []

    # Heuristic 1: growth + weak quality.
    if not snapshot.empty and not orders_growth.empty:
        quality = snapshot[snapshot["metric"] == "Perfect Orders"][
            ["country", "city", "zone", "value"]
        ].rename(columns={"value": "perfect_orders"})
        country_median = quality.groupby("country", as_index=False)["perfect_orders"].median().rename(
            columns={"perfect_orders": "country_perfect_orders_median"}
        )
        growth_quality = (
            orders_growth.merge(quality, on=["country", "city", "zone"], how="inner")
            .merge(country_median, on="country", how="left")
            .dropna(subset=["country_perfect_orders_median"])
        )

        flagged = growth_quality[
            (growth_quality["orders_growth_pct"] >= 0.10)
            & (growth_quality["perfect_orders"] < growth_quality["country_perfect_orders_median"])
        ]
        for _, row in flagged.iterrows():
            growth_pct = float(row["orders_growth_pct"])
            perfect_orders = float(row["perfect_orders"])
            median = float(row["country_perfect_orders_median"])
            excess = max(0.0, growth_pct - 0.10)
            quality_gap = max(0.0, (median - perfect_orders) / abs(median) if abs(median) > 1e-9 else 0.0)
            severity = min(100.0, excess * 260.0 + quality_gap * 120.0 + 25.0)
            insights.append(
                cast(
                    InsightItem,
                    make_insight(
                        category="opportunities",
                        title="Growth momentum with quality risk",
                        metric="Orders + Perfect Orders",
                        country=str(row["country"]),
                        city=str(row["city"]),
                        zone=str(row["zone"]),
                        severity_score=severity,
                        summary=(
                            f"Orders are growing quickly in {row['zone']} while Perfect Orders are below the country median."
                        ),
                        evidence={
                            "orders_growth_pct": growth_pct,
                            "perfect_orders": perfect_orders,
                            "country_perfect_orders_median": median,
                            "affected_zones_count": 1,
                        },
                        recommendation_hint=(
                            "Protect growth by prioritizing quality safeguards in this zone before scaling demand."
                        ),
                    ),
                )
            )

    # Heuristic 2: strong quality + low penetration.
    wide_quality_penetration = _wide_metrics(snapshot, ["Perfect Orders", "Lead Penetration"])
    if not wide_quality_penetration.empty:
        for country, country_df in wide_quality_penetration.groupby("country", dropna=False):
            if "Perfect Orders" not in country_df.columns or "Lead Penetration" not in country_df.columns:
                continue
            p75_quality = country_df["Perfect Orders"].quantile(0.75)
            p25_penetration = country_df["Lead Penetration"].quantile(0.25)

            flagged = country_df[
                (country_df["Perfect Orders"] >= p75_quality)
                & (country_df["Lead Penetration"] <= p25_penetration)
            ]
            for _, row in flagged.iterrows():
                quality = float(row["Perfect Orders"])
                penetration = float(row["Lead Penetration"])
                quality_excess = max(0.0, (quality - p75_quality) / abs(p75_quality) if abs(p75_quality) > 1e-9 else 0.0)
                penetration_gap = max(
                    0.0,
                    (p25_penetration - penetration) / abs(p25_penetration) if abs(p25_penetration) > 1e-9 else 0.0,
                )
                severity = min(100.0, 30.0 + quality_excess * 120.0 + penetration_gap * 140.0)
                insights.append(
                    cast(
                        InsightItem,
                        make_insight(
                            category="opportunities",
                            title="High quality with low penetration upside",
                            metric="Perfect Orders + Lead Penetration",
                            country=str(country),
                            city=str(row["city"]),
                            zone=str(row["zone"]),
                            severity_score=severity,
                            summary=(
                                f"{row['zone']} combines strong quality with low penetration, suggesting expansion potential."
                            ),
                            evidence={
                                "perfect_orders": quality,
                                "lead_penetration": penetration,
                                "country_quality_p75": float(p75_quality),
                                "country_penetration_p25": float(p25_penetration),
                                "affected_zones_count": 1,
                            },
                            recommendation_hint=(
                                "Test targeted acquisition and assortment actions to convert quality strength into broader penetration."
                            ),
                        ),
                    )
                )

    # Heuristic 3: replication candidate.
    wide_replication = _wide_metrics(snapshot, ["Gross Profit UE", "Turbo Adoption"])
    if not wide_replication.empty and "Gross Profit UE" in wide_replication and "Turbo Adoption" in wide_replication:
        for country, country_df in wide_replication.groupby("country", dropna=False):
            gp_decile = country_df["Gross Profit UE"].quantile(0.90)
            turbo_median = country_df["Turbo Adoption"].median()
            flagged = country_df[
                (country_df["Gross Profit UE"] >= gp_decile)
                & (country_df["Turbo Adoption"] > turbo_median)
            ]
            for _, row in flagged.iterrows():
                gp = float(row["Gross Profit UE"])
                turbo = float(row["Turbo Adoption"])
                gp_excess = max(0.0, (gp - gp_decile) / abs(gp_decile) if abs(gp_decile) > 1e-9 else 0.0)
                turbo_excess = max(
                    0.0, (turbo - turbo_median) / abs(turbo_median) if abs(turbo_median) > 1e-9 else 0.0
                )
                severity = min(100.0, 25.0 + gp_excess * 160.0 + turbo_excess * 100.0)
                insights.append(
                    cast(
                        InsightItem,
                        make_insight(
                            category="opportunities",
                            title="Replication candidate zone",
                            metric="Gross Profit UE + Turbo Adoption",
                            country=str(country),
                            city=str(row["city"]),
                            zone=str(row["zone"]),
                            severity_score=severity,
                            summary=(
                                f"{row['zone']} is in the top decile for Gross Profit UE and above median Turbo Adoption in {country}."
                            ),
                            evidence={
                                "gross_profit_ue": gp,
                                "turbo_adoption": turbo,
                                "country_gp_top_decile": float(gp_decile),
                                "country_turbo_median": float(turbo_median),
                                "affected_zones_count": 1,
                            },
                            recommendation_hint=(
                                "Document this operating playbook and replicate it in peer zones with similar demand profiles."
                            ),
                        ),
                    )
                )

    insights.sort(key=lambda item: item["severity_score"], reverse=True)
    return insights[:max_insights]

