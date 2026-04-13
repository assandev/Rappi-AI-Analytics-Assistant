"""Generate automatic insights report from processed datasets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.insights.service import generate_and_save_insights_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate executive markdown insights report.")
    parser.add_argument(
        "--output",
        default="reports/insights_report.md",
        help="Output markdown path.",
    )
    parser.add_argument(
        "--top-k-critical",
        type=int,
        default=5,
        help="Number of critical insights to prioritize (bounded to 3-5).",
    )
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="Skip LLM and always use deterministic markdown fallback.",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    args = parse_args()
    result = generate_and_save_insights_report(
        output_path=PROJECT_ROOT / args.output,
        top_k_critical=args.top_k_critical,
        force_fallback=args.force_fallback,
    )

    print("Insights report generated successfully.")
    print(f"Output path: {result['output_path']}")
    print(f"Total insights: {result['insight_count']}")
    print(f"Top critical count: {len(result['top_critical_titles'])}")
    print(f"Counts by category: {result['category_counts']}")
    if result["top_critical_titles"]:
        print("Top critical titles:")
        for title in result["top_critical_titles"]:
            print(f" - {title}")


if __name__ == "__main__":
    main()
