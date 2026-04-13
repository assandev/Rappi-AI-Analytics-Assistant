"""Prepare normalized analytical CSVs from the Rappi dummy workbook."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


REQUIRED_SHEETS = ("raw_input_metrics", "raw_orders")
OPTIONAL_IGNORED_SHEETS = ("raw_summary",)
METRICS_OUTPUT_COLUMNS = [
    "country",
    "city",
    "zone",
    "zone_type",
    "zone_prioritization",
    "metric",
    "week",
    "week_label",
    "value",
]
ORDERS_OUTPUT_COLUMNS = [
    "country",
    "city",
    "zone",
    "metric",
    "week",
    "week_label",
    "value",
]
WEEK_COLUMN_REGEX = re.compile(r"^l(\d+)w(?:_roll)?$")
RAW_WEEK_COLUMN_REGEX = re.compile(r"^l(\d+)w$")
ROLL_WEEK_COLUMN_REGEX = re.compile(r"^l(\d+)w_roll$")


def canonicalize_name(value: str) -> str:
    """Normalize strings to lowercase snake_case style."""
    text = str(value).strip().lower()
    text = re.sub(r"[^\w]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def resolve_default_workbook(root_dir: Path) -> Path:
    """Resolve workbook path when no explicit --workbook is provided."""
    xlsx_files = sorted(root_dir.glob("*.xlsx"))
    if not xlsx_files:
        raise FileNotFoundError("No .xlsx file found in project root.")
    if len(xlsx_files) == 1:
        return xlsx_files[0]
    expected = [
        p
        for p in xlsx_files
        if "rappi" in canonicalize_name(p.stem) and "dummy" in canonicalize_name(p.stem)
    ]
    if len(expected) == 1:
        return expected[0]
    names = ", ".join(p.name for p in xlsx_files)
    raise FileNotFoundError(
        "Multiple .xlsx files detected. Pass --workbook explicitly. "
        f"Detected: {names}"
    )


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with normalized lowercase snake_case column names."""
    normalized = df.copy()
    normalized.columns = [canonicalize_name(col) for col in normalized.columns]
    return normalized


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Trim string values, convert blank strings to null, and drop fully empty rows."""
    cleaned = df.copy()
    # Include both legacy object dtype and newer string dtype to avoid pandas
    # deprecation warnings while preserving the same cleaning behavior.
    object_columns = cleaned.select_dtypes(include=["object", "string"]).columns
    for col in object_columns:
        cleaned[col] = cleaned[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
    cleaned = cleaned.replace(r"^\s*$", pd.NA, regex=True)
    cleaned = cleaned.dropna(how="all")
    return cleaned


def detect_week_columns(
    columns: Iterable[str], prefer_roll: bool = True
) -> Tuple[List[str], List[str], List[str], str]:
    """Detect and select week columns, preferring roll representation when available."""
    normalized_columns = [str(col).strip().lower() for col in columns]
    raw_columns = [col for col in normalized_columns if RAW_WEEK_COLUMN_REGEX.match(col)]
    roll_columns = [col for col in normalized_columns if ROLL_WEEK_COLUMN_REGEX.match(col)]

    raw_columns = sorted(raw_columns, key=extract_week_number, reverse=True)
    roll_columns = sorted(roll_columns, key=extract_week_number, reverse=True)

    if prefer_roll and roll_columns:
        return roll_columns, raw_columns, roll_columns, "roll_preferred"
    if raw_columns:
        return raw_columns, raw_columns, roll_columns, "raw_fallback"
    if roll_columns:
        return roll_columns, raw_columns, roll_columns, "roll_only"
    return [], raw_columns, roll_columns, "none_found"


def extract_week_number(column_name: str) -> int:
    """Extract integer week number from a week column."""
    match = WEEK_COLUMN_REGEX.match(column_name)
    if not match:
        raise ValueError(f"Invalid week column: {column_name}")
    return int(match.group(1))


def find_required_columns(
    df: pd.DataFrame, required: Iterable[str], context: str
) -> List[str]:
    """Validate required columns exist and return missing list if any."""
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"{context} missing required columns: {missing}")
    return missing


def load_workbook(workbook_path: Path) -> Dict[str, pd.DataFrame]:
    """Load required workbook sheets with case-insensitive sheet matching."""
    if not workbook_path.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook_path}")

    try:
        excel_file = pd.ExcelFile(workbook_path)
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'openpyxl'. Install it with: pip install openpyxl"
        ) from exc

    detected = excel_file.sheet_names
    print(f"Detected sheet names: {detected}")

    normalized_sheet_map: Dict[str, str] = {}
    for sheet_name in detected:
        key = canonicalize_name(sheet_name)
        normalized_sheet_map[key] = sheet_name

    dataframes: Dict[str, pd.DataFrame] = {}
    for required in REQUIRED_SHEETS:
        if required not in normalized_sheet_map:
            raise ValueError(
                f"Required sheet '{required}' was not found. "
                f"Detected sheets: {detected}"
            )
        actual = normalized_sheet_map[required]
        print(f"Resolved sheet '{required}' -> '{actual}'")
        dataframes[required] = pd.read_excel(workbook_path, sheet_name=actual)

    for optional in OPTIONAL_IGNORED_SHEETS:
        if optional in normalized_sheet_map:
            actual = normalized_sheet_map[optional]
            print(
                f"Detected optional sheet '{actual}' (canonical: '{optional}'). "
                "Ignoring it for the core analytical pipeline."
            )

    return dataframes


def reshape_metrics_sheet(df: pd.DataFrame) -> pd.DataFrame:
    """Transform raw_input_metrics into long canonical format."""
    normalized = clean_dataframe(normalize_columns(df))
    print(f"raw_input_metrics raw rows (after dropping fully empty): {len(normalized)}")

    required_identifiers = [
        "country",
        "city",
        "zone",
        "zone_type",
        "zone_prioritization",
        "metric",
    ]
    find_required_columns(normalized, required_identifiers, "raw_input_metrics")

    week_columns, raw_week_columns, roll_week_columns, selection_strategy = (
        detect_week_columns(normalized.columns, prefer_roll=True)
    )
    if not week_columns:
        raise ValueError("raw_input_metrics has no week columns matching L#W or L#W_ROLL.")
    print(f"raw_input_metrics detected raw week columns: {len(raw_week_columns)} ({raw_week_columns})")
    print(
        f"raw_input_metrics detected roll week columns: {len(roll_week_columns)} ({roll_week_columns})"
    )
    print(
        f"raw_input_metrics selected week columns ({selection_strategy}): "
        f"{len(week_columns)} ({week_columns})"
    )

    melted = normalized.melt(
        id_vars=required_identifiers,
        value_vars=week_columns,
        var_name="week_label",
        value_name="value",
    )
    melted["week"] = melted["week_label"].apply(extract_week_number).astype("int64")
    melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
    melted = melted.dropna(subset=["value"])
    melted = clean_dataframe(melted)

    metrics_long = melted[METRICS_OUTPUT_COLUMNS].copy()
    metrics_long = collapse_metrics_duplicate_grain(metrics_long)
    print(f"metrics_long output rows: {len(metrics_long)}")
    return metrics_long


def reshape_orders_sheet(df: pd.DataFrame) -> pd.DataFrame:
    """Transform raw_orders into long canonical format."""
    normalized = clean_dataframe(normalize_columns(df))
    print(f"raw_orders raw rows (after dropping fully empty): {len(normalized)}")

    required_identifiers = ["country", "city", "zone"]
    find_required_columns(normalized, required_identifiers, "raw_orders")

    if "metric" not in normalized.columns:
        normalized["metric"] = "Orders"
    normalized["metric"] = normalized["metric"].fillna("Orders")
    normalized["metric"] = normalized["metric"].apply(
        lambda v: "Orders" if not isinstance(v, str) or not v.strip() else v.strip()
    )

    week_columns, raw_week_columns, roll_week_columns, selection_strategy = (
        detect_week_columns(normalized.columns, prefer_roll=True)
    )
    if not week_columns:
        raise ValueError("raw_orders has no week columns matching L#W or L#W_ROLL.")
    print(f"raw_orders detected raw week columns: {len(raw_week_columns)} ({raw_week_columns})")
    print(f"raw_orders detected roll week columns: {len(roll_week_columns)} ({roll_week_columns})")
    print(
        f"raw_orders selected week columns ({selection_strategy}): "
        f"{len(week_columns)} ({week_columns})"
    )

    melted = normalized.melt(
        id_vars=required_identifiers + ["metric"],
        value_vars=week_columns,
        var_name="week_label",
        value_name="value",
    )
    melted["week"] = melted["week_label"].apply(extract_week_number).astype("int64")
    melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
    melted = melted.dropna(subset=["value"])
    melted = clean_dataframe(melted)

    orders_long = melted[ORDERS_OUTPUT_COLUMNS].copy()
    print(f"orders_long output rows: {len(orders_long)}")
    return orders_long


def _first_non_null(series: pd.Series):
    """Return first non-null item or pd.NA."""
    non_null = series.dropna()
    return non_null.iloc[0] if not non_null.empty else pd.NA


def collapse_metrics_duplicate_grain(metrics_long: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicated metrics analytical grain deterministically."""
    key_columns = ["country", "city", "zone", "metric", "week"]
    duplicate_count = int(metrics_long.duplicated(subset=key_columns, keep=False).sum())
    if duplicate_count == 0:
        return metrics_long

    print(
        "metrics_long duplicate grain detected before collapse: "
        f"{duplicate_count} rows on key {key_columns}"
    )
    collapsed = (
        metrics_long.groupby(key_columns, as_index=False)
        .agg(
            zone_type=("zone_type", _first_non_null),
            zone_prioritization=("zone_prioritization", _first_non_null),
            week_label=("week_label", _first_non_null),
            value=("value", "mean"),
        )
        .loc[:, METRICS_OUTPUT_COLUMNS]
    )
    post_duplicate_count = int(
        collapsed.duplicated(subset=key_columns, keep=False).sum()
    )
    print(
        "metrics_long duplicate grain after collapse: "
        f"{post_duplicate_count} rows on key {key_columns}"
    )
    return collapsed


def build_geography_lookup(metrics_long: pd.DataFrame) -> pd.DataFrame:
    """Create geography lookup with zone_type and zone_prioritization."""
    lookup = (
        metrics_long.groupby(["country", "city", "zone"], as_index=False)[
            ["zone_type", "zone_prioritization"]
        ]
        .agg(_first_non_null)
        .drop_duplicates()
    )
    return lookup


def build_analytics_base(metrics_long: pd.DataFrame, orders_long: pd.DataFrame) -> pd.DataFrame:
    """Combine metrics and orders into one enriched analytical base table."""
    geography_lookup = build_geography_lookup(metrics_long)
    orders_enriched = orders_long.merge(
        geography_lookup, on=["country", "city", "zone"], how="left"
    )
    orders_enriched = orders_enriched[
        [
            "country",
            "city",
            "zone",
            "zone_type",
            "zone_prioritization",
            "metric",
            "week",
            "week_label",
            "value",
        ]
    ]
    analytics_base = pd.concat([metrics_long, orders_enriched], ignore_index=True)
    analytics_base = clean_dataframe(analytics_base)
    return analytics_base[METRICS_OUTPUT_COLUMNS]


def build_metrics_features(metrics_long: pd.DataFrame) -> pd.DataFrame:
    """Build optional point-in-time feature table from metrics_long."""
    index_cols = ["country", "city", "zone", "metric"]
    pivot = metrics_long.pivot_table(
        index=index_cols,
        columns="week",
        values="value",
        aggfunc="mean",
    ).reset_index()
    pivot.columns.name = None

    features = pivot.copy()
    features["current_value"] = features[0] if 0 in features.columns else pd.NA
    features["value_1w_ago"] = features[1] if 1 in features.columns else pd.NA
    features["value_5w_ago"] = features[5] if 5 in features.columns else pd.NA
    features["delta_1w"] = features["current_value"] - features["value_1w_ago"]
    features["delta_5w"] = features["current_value"] - features["value_5w_ago"]

    final_columns = index_cols + [
        "current_value",
        "value_1w_ago",
        "value_5w_ago",
        "delta_1w",
        "delta_5w",
    ]
    return features[final_columns]


def save_csv(df: pd.DataFrame, path: Path) -> None:
    """Save dataframe as UTF-8 CSV and print output information."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    print(f"Saved {len(df)} rows -> {path}")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Prepare canonical analytical CSVs.")
    parser.add_argument(
        "--workbook",
        type=Path,
        default=None,
        help="Path to source workbook (.xlsx). Defaults to auto-resolved file in project root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="Output directory for processed CSVs.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the data preparation pipeline end-to-end."""
    args = parse_args()
    root_dir = Path.cwd()
    workbook_path = args.workbook if args.workbook else resolve_default_workbook(root_dir)
    print(f"Using workbook: {workbook_path}")

    sheets = load_workbook(workbook_path)
    metrics_long = reshape_metrics_sheet(sheets["raw_input_metrics"])
    orders_long = reshape_orders_sheet(sheets["raw_orders"])
    analytics_base = build_analytics_base(metrics_long, orders_long)
    metrics_features = build_metrics_features(metrics_long)

    output_dir = args.output_dir
    save_csv(metrics_long, output_dir / "metrics_long.csv")
    save_csv(orders_long, output_dir / "orders_long.csv")
    save_csv(analytics_base, output_dir / "analytics_base.csv")
    save_csv(metrics_features, output_dir / "metrics_features.csv")

    print("Data preparation completed successfully.")


if __name__ == "__main__":
    main()
