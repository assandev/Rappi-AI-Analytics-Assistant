"""Runnable diagnostic tests for anomalies, trends, and benchmarking detectors."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.insights.detectors.anomalies import detect_anomalies
from src.insights.detectors.benchmarking import detect_benchmarking_gaps
from src.insights.detectors.trends import detect_concerning_trends


def _empty_orders_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["country", "city", "zone", "metric", "week", "value"])


def run_anomalies_case() -> tuple[bool, str]:
    metrics_df = pd.DataFrame(
        [
            {
                "country": "CO",
                "city": "Bogota",
                "zone": "Chapinero",
                "zone_type": "Wealthy",
                "zone_prioritization": "Prioritized",
                "metric": "Lead Penetration",
                "week": 1,
                "value": 100.0,
            },
            {
                "country": "CO",
                "city": "Bogota",
                "zone": "Chapinero",
                "zone_type": "Wealthy",
                "zone_prioritization": "Prioritized",
                "metric": "Lead Penetration",
                "week": 0,
                "value": 130.0,
            },
        ]
    )
    insights = detect_anomalies(metrics_df, _empty_orders_df())
    if not insights:
        return False, "No anomalies detected."
    pct_change = insights[0]["evidence"].get("pct_change")
    if pct_change is None or float(pct_change) < 0.10:
        return False, f"Unexpected pct_change in anomaly evidence: {pct_change}"
    return True, f"Detected anomaly with pct_change={float(pct_change):.2f}"


def run_trends_case() -> tuple[bool, str]:
    metrics_df = pd.DataFrame(
        [
            {
                "country": "MX",
                "city": "CDMX",
                "zone": "Roma",
                "zone_type": "Wealthy",
                "zone_prioritization": "Prioritized",
                "metric": "Perfect Orders",
                "week": 3,
                "value": 1.00,
            },
            {
                "country": "MX",
                "city": "CDMX",
                "zone": "Roma",
                "zone_type": "Wealthy",
                "zone_prioritization": "Prioritized",
                "metric": "Perfect Orders",
                "week": 2,
                "value": 0.90,
            },
            {
                "country": "MX",
                "city": "CDMX",
                "zone": "Roma",
                "zone_type": "Wealthy",
                "zone_prioritization": "Prioritized",
                "metric": "Perfect Orders",
                "week": 1,
                "value": 0.80,
            },
            {
                "country": "MX",
                "city": "CDMX",
                "zone": "Roma",
                "zone_type": "Wealthy",
                "zone_prioritization": "Prioritized",
                "metric": "Perfect Orders",
                "week": 0,
                "value": 0.70,
            },
        ]
    )
    insights = detect_concerning_trends(metrics_df, _empty_orders_df())
    if not insights:
        return False, "No concerning trend detected."
    run_length = insights[0]["evidence"].get("run_length")
    if run_length is None or int(run_length) < 3:
        return False, f"Unexpected run_length in trend evidence: {run_length}"
    return True, f"Detected concerning trend with run_length={int(run_length)}"


def run_benchmarking_case() -> tuple[bool, str]:
    rows = []
    base_values = [100.0, 102.0, 98.0, 101.0, 99.0]
    for idx, value in enumerate(base_values, start=1):
        rows.append(
            {
                "country": "CO",
                "city": "Bogota",
                "zone": f"Peer-{idx}",
                "zone_type": "Non Wealthy",
                "zone_prioritization": "Not Prioritized",
                "metric": "Lead Penetration",
                "week": 0,
                "value": value,
            }
        )
    rows.append(
        {
            "country": "CO",
            "city": "Bogota",
            "zone": "Outlier-Zone",
            "zone_type": "Non Wealthy",
            "zone_prioritization": "Not Prioritized",
            "metric": "Lead Penetration",
            "week": 0,
            "value": 140.0,
        }
    )
    metrics_df = pd.DataFrame(rows)
    insights = detect_benchmarking_gaps(metrics_df, _empty_orders_df(), min_peer_count=5)
    if not insights:
        return False, "No benchmarking gap detected."
    gap_pct = insights[0]["evidence"].get("gap_pct")
    if gap_pct is None or abs(float(gap_pct)) < 0.15:
        return False, f"Unexpected gap_pct in benchmarking evidence: {gap_pct}"
    return True, f"Detected benchmarking gap with gap_pct={float(gap_pct):.2f}"


def main() -> None:
    tests = [
        ("Anomalies", run_anomalies_case),
        ("Trends", run_trends_case),
        ("Benchmarking", run_benchmarking_case),
    ]

    failures = 0
    for name, test_fn in tests:
        ok, message = test_fn()
        if ok:
            print(f"PASS | {name} | {message}")
        else:
            failures += 1
            print(f"FAIL | {name} | {message}")

    if failures:
        raise SystemExit(1)
    print("All insight detector tests passed.")


if __name__ == "__main__":
    main()

