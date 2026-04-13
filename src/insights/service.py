"""Shared service for generating and persisting insights markdown reports."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from openai import OpenAI

from src.insights import run_insight_engine
from src.insights.report_generator import generate_markdown_report, save_markdown_report


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "reports" / "insights_report.md"


def load_processed_datasets() -> dict[str, pd.DataFrame]:
    """Load processed datasets from canonical project location."""
    metrics_path = PROCESSED_DIR / "metrics_long.csv"
    orders_path = PROCESSED_DIR / "orders_long.csv"
    if not metrics_path.exists() or not orders_path.exists():
        raise FileNotFoundError("Missing processed datasets. Run scripts/prepare_data.py first.")
    return {
        "metrics_long": pd.read_csv(metrics_path),
        "orders_long": pd.read_csv(orders_path),
    }


def build_insights_llm_callable() -> Callable[..., str]:
    """Build OpenAI-compatible callable for insights markdown generation."""
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    base_url = os.getenv("OPENAI_BASE_URL")
    is_local_compatible = bool(base_url) or provider in {"local_openai_compatible", "ollama", "local"}

    default_model = "llama3.1" if is_local_compatible else "gpt-4o-mini"
    model = os.getenv("INSIGHTS_REPORT_MODEL", os.getenv("OPENAI_MODEL", default_model))
    temperature = float(os.getenv("INSIGHTS_REPORT_TEMPERATURE", "0"))

    api_key = os.getenv("OPENAI_API_KEY")
    if is_local_compatible:
        api_key = api_key or "local-dev-key"
    elif not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI cloud mode.")

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def _call(system_prompt: str, user_prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content if response.choices else "") or ""

    return _call


def generate_and_save_insights_report(
    *,
    datasets: dict[str, pd.DataFrame] | None = None,
    output_path: str | Path | None = None,
    top_k_critical: int = 5,
    force_fallback: bool = False,
) -> dict[str, Any]:
    """Generate insights markdown and save it to disk."""
    datasets_to_use = datasets if datasets is not None else load_processed_datasets()
    bounded_top_k = min(5, max(3, int(top_k_critical)))
    payload = run_insight_engine(datasets_to_use, top_k_critical=bounded_top_k)
    llm_callable = None if force_fallback else build_insights_llm_callable()
    markdown = generate_markdown_report(payload, llm_callable=llm_callable)

    final_output_path = Path(output_path) if output_path else DEFAULT_REPORT_PATH
    if not final_output_path.is_absolute():
        final_output_path = PROJECT_ROOT / final_output_path
    saved_path = save_markdown_report(markdown, final_output_path)

    return {
        "markdown": markdown,
        "output_path": str(saved_path),
        "insight_count": payload["insight_count"],
        "top_critical_titles": [item["title"] for item in payload["executive_summary_insights"]],
        "generated_at": payload["generated_at"],
        "top_k_critical": bounded_top_k,
        "category_counts": {
            category: len(items) for category, items in payload["insights_by_category"].items()
        },
        "curation_metadata": payload["curation_metadata"],
    }
