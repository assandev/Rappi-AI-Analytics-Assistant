"""Validation script for processed analytical datasets."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import pandas as pd


EXPECTED_SCHEMAS: Dict[str, List[str]] = {
    "metrics_long": [
        "country",
        "city",
        "zone",
        "zone_type",
        "zone_prioritization",
        "metric",
        "week",
        "week_label",
        "value",
    ],
    "orders_long": [
        "country",
        "city",
        "zone",
        "metric",
        "week",
        "week_label",
        "value",
    ],
    "analytics_base": [
        "country",
        "city",
        "zone",
        "zone_type",
        "zone_prioritization",
        "metric",
        "week",
        "week_label",
        "value",
    ],
    "metrics_features": [
        "country",
        "city",
        "zone",
        "metric",
        "current_value",
        "value_1w_ago",
        "value_5w_ago",
        "delta_1w",
        "delta_5w",
    ],
}

CRITICAL_FIELDS = ["country", "city", "zone", "metric", "week", "value"]
WEEK_LABEL_PATTERN = r"^l[0-8]w(?:_roll)?$"


@dataclass
class ValidationTracker:
    """Track validation findings and final status."""

    critical_issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_critical(self, message: str) -> None:
        self.critical_issues.append(message)
        print(f"[CRITICAL] {message}")

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)
        print(f"[WARN] {message}")

    def final_status(self) -> str:
        if self.critical_issues:
            return "FAIL"
        if self.warnings:
            return "WARN"
        return "PASS"


def print_section(title: str) -> None:
    """Print a section title with separators."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def check_file_exists(path: Path) -> None:
    """Validate file existence."""
    if not path.exists():
        raise FileNotFoundError(f"Required file is missing: {path}")


def load_csv(path: Path) -> pd.DataFrame:
    """Load CSV into DataFrame."""
    return pd.read_csv(path)


def validate_required_columns(
    df: pd.DataFrame, expected_columns: Sequence[str], dataset_name: str
) -> None:
    """Fail clearly if required columns are missing."""
    missing = [column for column in expected_columns if column not in df.columns]
    if missing:
        raise ValueError(
            f"{dataset_name} is missing required columns: {missing}. "
            f"Available columns: {list(df.columns)}"
        )


def check_nulls(
    df: pd.DataFrame,
    columns: Sequence[str],
    dataset_name: str,
    tracker: ValidationTracker,
) -> None:
    """Print null counts for critical fields and flag major null rates."""
    print(f"{dataset_name} null counts:")
    for column in columns:
        null_count = int(df[column].isna().sum())
        print(f"  - {column}: {null_count}")
        if null_count > 0:
            ratio = null_count / max(len(df), 1)
            if ratio >= 0.05:
                tracker.add_critical(
                    f"{dataset_name}.{column} has high null rate ({ratio:.2%})."
                )
            else:
                tracker.add_warning(
                    f"{dataset_name}.{column} has {null_count} null values ({ratio:.2%})."
                )


def check_week_values(df: pd.DataFrame, dataset_name: str, tracker: ValidationTracker) -> None:
    """Validate week numeric range and week_label pattern."""
    week_numeric = pd.to_numeric(df["week"], errors="coerce")
    non_numeric_count = int(week_numeric.isna().sum())
    distinct_week_values = sorted(week_numeric.dropna().unique().tolist())
    distinct_week_labels = sorted(df["week_label"].dropna().astype(str).unique().tolist())

    print(f"{dataset_name} distinct week values: {distinct_week_values}")
    print(f"{dataset_name} distinct week labels: {distinct_week_labels}")

    if non_numeric_count > 0:
        tracker.add_critical(
            f"{dataset_name}.week contains {non_numeric_count} non-numeric values."
        )

    invalid_range = df.loc[~week_numeric.isna() & ~week_numeric.between(0, 8), ["week"]]
    if not invalid_range.empty:
        tracker.add_critical(
            f"{dataset_name}.week has values outside 0-8 (count={len(invalid_range)})."
        )
        print("Sample invalid week rows:")
        print(invalid_range.head(10).to_string(index=False))

    invalid_labels = df.loc[
        ~df["week_label"].astype(str).str.fullmatch(WEEK_LABEL_PATTERN, na=False),
        ["week_label"],
    ]
    if not invalid_labels.empty:
        tracker.add_warning(
            f"{dataset_name}.week_label has unexpected format values (count={len(invalid_labels)})."
        )
        print("Sample invalid week_label values:")
        print(invalid_labels.drop_duplicates().head(10).to_string(index=False))


def check_duplicates(
    df: pd.DataFrame,
    key_columns: Sequence[str],
    dataset_name: str,
    tracker: ValidationTracker,
) -> int:
    """Check duplicate counts for analytical grain and print samples."""
    duplicate_mask = df.duplicated(subset=key_columns, keep=False)
    duplicate_count = int(duplicate_mask.sum())
    duplicate_groups = (
        df.loc[duplicate_mask, list(key_columns)]
        .value_counts()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )
    duplicate_group_count = len(duplicate_groups)

    print(
        f"{dataset_name} duplicate rows on {list(key_columns)}: "
        f"{duplicate_count} rows across {duplicate_group_count} duplicate keys"
    )

    if duplicate_count > 0:
        tracker.add_critical(
            f"{dataset_name} has duplicated analytical grain ({duplicate_group_count} keys)."
        )
        print("Top duplicate keys:")
        print(duplicate_groups.head(10).to_string(index=False))
        print("Sample duplicate rows:")
        print(df.loc[duplicate_mask].head(10).to_string(index=False))

    return duplicate_count


def build_geography_lookup(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Build geography lookup from metrics data."""
    cols = ["country", "city", "zone", "zone_type", "zone_prioritization"]
    return metrics_df[cols].drop_duplicates()


def check_geography_consistency(
    geo_lookup: pd.DataFrame, tracker: ValidationTracker
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Check one-to-one mapping of geography to metadata."""
    type_conflicts = (
        geo_lookup.groupby(["country", "city", "zone"])["zone_type"]
        .nunique(dropna=False)
        .reset_index(name="zone_type_nunique")
    )
    type_conflicts = type_conflicts[type_conflicts["zone_type_nunique"] > 1]

    prioritization_conflicts = (
        geo_lookup.groupby(["country", "city", "zone"])["zone_prioritization"]
        .nunique(dropna=False)
        .reset_index(name="zone_prioritization_nunique")
    )
    prioritization_conflicts = prioritization_conflicts[
        prioritization_conflicts["zone_prioritization_nunique"] > 1
    ]

    print(
        f"Conflicting zone_type mappings: {len(type_conflicts)} geographies | "
        f"Conflicting zone_prioritization mappings: {len(prioritization_conflicts)} geographies"
    )

    if not type_conflicts.empty:
        tracker.add_critical(
            "Geography conflicts found: some (country, city, zone) map to multiple zone_type values."
        )
        print("Sample zone_type conflicts:")
        print(type_conflicts.head(10).to_string(index=False))

    if not prioritization_conflicts.empty:
        tracker.add_critical(
            "Geography conflicts found: some (country, city, zone) map to multiple zone_prioritization values."
        )
        print("Sample zone_prioritization conflicts:")
        print(prioritization_conflicts.head(10).to_string(index=False))

    return type_conflicts, prioritization_conflicts


def check_orders_enrichment_safety(
    orders_df: pd.DataFrame, geo_lookup: pd.DataFrame, tracker: ValidationTracker
) -> None:
    """Validate orders enrichment join safety and matching quality."""
    keys = ["country", "city", "zone"]
    before = len(orders_df)
    joined = orders_df.merge(geo_lookup, on=keys, how="left", indicator=True)
    after = len(joined)
    merge_breakdown = joined["_merge"].value_counts(dropna=False).to_dict()

    print(f"Orders rows before join: {before}")
    print(f"Orders rows after join:  {after}")
    print(f"Merge indicator breakdown: {merge_breakdown}")

    if after > before:
        tracker.add_critical(
            f"Orders enrichment join multiplies rows (before={before}, after={after})."
        )

    unmatched = joined.loc[joined["_merge"] == "left_only", keys].drop_duplicates()
    unmatched_count = len(unmatched)
    print(f"Unmatched order geographies: {unmatched_count}")
    if unmatched_count > 0:
        tracker.add_warning(
            f"Orders enrichment has {unmatched_count} unmatched geographies."
        )
        print("Sample unmatched geographies:")
        print(unmatched.head(10).to_string(index=False))


def check_orders_in_analytics_base(
    orders_df: pd.DataFrame, analytics_df: pd.DataFrame, tracker: ValidationTracker
) -> None:
    """Check orders row integrity inside analytics_base."""
    orders_in_analytics = analytics_df[analytics_df["metric"].astype(str) == "Orders"]
    orders_count = len(orders_df)
    analytics_orders_count = len(orders_in_analytics)

    print(f"orders_long rows: {orders_count}")
    print(f"analytics_base Orders rows: {analytics_orders_count}")

    if analytics_orders_count > orders_count:
        tracker.add_critical(
            "Orders rows in analytics_base exceed orders_long rows. "
            "Possible enrichment duplication."
        )
    elif analytics_orders_count < orders_count:
        tracker.add_warning(
            "Orders rows in analytics_base are fewer than orders_long rows."
        )

    key_cols = ["country", "city", "zone", "metric", "week"]
    duplicate_mask = orders_in_analytics.duplicated(subset=key_cols, keep=False)
    duplicate_count = int(duplicate_mask.sum())
    print(f"analytics_base Orders duplicate rows on grain key: {duplicate_count}")
    if duplicate_count > 0:
        tracker.add_critical(
            "Orders rows inside analytics_base have duplicate analytical grain."
        )
        print("Sample duplicated Orders rows:")
        print(orders_in_analytics.loc[duplicate_mask].head(10).to_string(index=False))


def check_metric_inventory(
    metrics_df: pd.DataFrame,
    analytics_df: pd.DataFrame,
    orders_df: pd.DataFrame,
    tracker: ValidationTracker,
) -> None:
    """Print metric inventory and validate Orders presence behavior."""
    metrics_list = sorted(metrics_df["metric"].dropna().astype(str).unique().tolist())
    analytics_metrics = sorted(
        analytics_df["metric"].dropna().astype(str).unique().tolist()
    )
    orders_metrics = sorted(orders_df["metric"].dropna().astype(str).unique().tolist())

    print(f"Distinct metrics in metrics_long: {len(metrics_list)}")
    print(f"metrics_long metric list: {metrics_list}")
    print(f"Distinct metrics in analytics_base: {len(analytics_metrics)}")

    if "Orders" not in orders_metrics:
        tracker.add_warning("Orders metric not found in orders_long (exact 'Orders').")

    if "Orders" not in analytics_metrics:
        tracker.add_critical("Orders metric not found in analytics_base (exact 'Orders').")

    orders_in_metrics = int((metrics_df["metric"].astype(str) == "Orders").sum())
    if orders_in_metrics > 0:
        ratio = orders_in_metrics / max(len(metrics_df), 1)
        tracker.add_warning(
            f"'Orders' appears in metrics_long ({orders_in_metrics} rows, {ratio:.2%})."
        )
        if ratio > 0.5:
            tracker.add_critical(
                "Orders unexpectedly dominates metrics_long (>50% of rows)."
            )


def check_metrics_features(features_df: pd.DataFrame, tracker: ValidationTracker) -> None:
    """Validate optional metrics_features dataset if present."""
    print(f"metrics_features row count: {len(features_df)}")
    validate_required_columns(
        features_df, EXPECTED_SCHEMAS["metrics_features"], "metrics_features"
    )
    key_cols = ["country", "city", "zone", "metric"]
    duplicate_count = int(features_df.duplicated(subset=key_cols, keep=False).sum())
    print(f"metrics_features duplicate rows on {key_cols}: {duplicate_count}")
    if duplicate_count > 0:
        tracker.add_warning("metrics_features has duplicate rows on feature grain key.")


def main() -> None:
    """Run all processed data validations and print consolidated status."""
    tracker = ValidationTracker()
    project_root = Path.cwd()
    processed_dir = project_root / "data" / "processed"

    required_paths = {
        "metrics_long": processed_dir / "metrics_long.csv",
        "orders_long": processed_dir / "orders_long.csv",
        "analytics_base": processed_dir / "analytics_base.csv",
    }
    optional_path = processed_dir / "metrics_features.csv"

    print_section("FILE CHECKS")
    dataframes: Dict[str, pd.DataFrame] = {}
    for name, path in required_paths.items():
        check_file_exists(path)
        df = load_csv(path)
        dataframes[name] = df
        print(f"{name}:")
        print(f"  - path: {path}")
        print(f"  - rows: {len(df)}")
        print(f"  - columns: {list(df.columns)}")

    if optional_path.exists():
        features_df = load_csv(optional_path)
        print("metrics_features:")
        print(f"  - path: {optional_path}")
        print(f"  - rows: {len(features_df)}")
        print(f"  - columns: {list(features_df.columns)}")
    else:
        features_df = None
        print("metrics_features.csv not found (optional).")

    print_section("SCHEMA CHECKS")
    for dataset_name in ["metrics_long", "orders_long", "analytics_base"]:
        validate_required_columns(
            dataframes[dataset_name], EXPECTED_SCHEMAS[dataset_name], dataset_name
        )
        print(f"{dataset_name}: required schema OK")

    print_section("NULL CHECKS")
    check_nulls(dataframes["metrics_long"], CRITICAL_FIELDS, "metrics_long", tracker)
    check_nulls(dataframes["orders_long"], CRITICAL_FIELDS, "orders_long", tracker)
    check_nulls(dataframes["analytics_base"], CRITICAL_FIELDS, "analytics_base", tracker)

    print_section("WEEK CHECKS")
    check_week_values(dataframes["metrics_long"], "metrics_long", tracker)
    check_week_values(dataframes["orders_long"], "orders_long", tracker)
    check_week_values(dataframes["analytics_base"], "analytics_base", tracker)

    print_section("DUPLICATE CHECKS")
    grain = ["country", "city", "zone", "metric", "week"]
    check_duplicates(dataframes["metrics_long"], grain, "metrics_long", tracker)
    check_duplicates(dataframes["orders_long"], grain, "orders_long", tracker)
    check_duplicates(dataframes["analytics_base"], grain, "analytics_base", tracker)

    print_section("GEOGRAPHY CONSISTENCY")
    geography_lookup = build_geography_lookup(dataframes["metrics_long"])
    print(f"Geography lookup rows: {len(geography_lookup)}")
    check_geography_consistency(geography_lookup, tracker)

    print_section("ENRICHMENT SAFETY")
    check_orders_enrichment_safety(dataframes["orders_long"], geography_lookup, tracker)

    print_section("ANALYTICS BASE ORDERS CHECK")
    check_orders_in_analytics_base(
        dataframes["orders_long"], dataframes["analytics_base"], tracker
    )

    print_section("METRIC CHECKS")
    check_metric_inventory(
        dataframes["metrics_long"],
        dataframes["analytics_base"],
        dataframes["orders_long"],
        tracker,
    )

    print_section("OPTIONAL FEATURES CHECK")
    if features_df is not None:
        check_metrics_features(features_df, tracker)
    else:
        print("Skipped (metrics_features.csv not present).")

    print_section("VALIDATION SUMMARY")
    print(f"Critical issues: {len(tracker.critical_issues)}")
    print(f"Warnings: {len(tracker.warnings)}")
    print(f"Final status: {tracker.final_status()}")

    if tracker.critical_issues:
        print("\nCritical issue list:")
        for issue in tracker.critical_issues:
            print(f"  - {issue}")

    if tracker.warnings:
        print("\nWarning list:")
        for warning in tracker.warnings:
            print(f"  - {warning}")


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as exc:
        print_section("VALIDATION FAILED EARLY")
        print(str(exc))
        sys.exit(1)
