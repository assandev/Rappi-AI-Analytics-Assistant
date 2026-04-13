"""FastAPI app that serves analytics API and built frontend in one process."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from app.services.execution import execute_query
from app.services.query_parser import parse_question_to_json
from app.services.query_validator import normalize_parsed_payload, validate_parsed_query
from src.insights.service import DEFAULT_REPORT_PATH, generate_and_save_insights_report
from src.response.response_formatter import format_response_with_llm


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


class QueryRequest(BaseModel):
    """HTTP input payload for chatbot execution."""

    question: str = Field(min_length=1)
    conversation_context: dict[str, Any] | None = None


class InsightsReportRequest(BaseModel):
    """HTTP input payload for one-click insights report generation."""

    top_k_critical: int = Field(default=5, ge=3, le=5)
    force_fallback: bool = False


def _build_formatter_llm_callable() -> Callable[..., str]:
    """Create OpenAI-compatible callable for final response formatting."""
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    base_url = os.getenv("OPENAI_BASE_URL")
    is_local_compatible = bool(base_url) or provider in {"local_openai_compatible", "ollama", "local"}
    default_model = "llama3.1" if is_local_compatible else "gpt-4o-mini"
    model = os.getenv("OPENAI_FORMATTER_MODEL", os.getenv("OPENAI_MODEL", default_model))
    temperature = float(os.getenv("FORMATTER_TEMPERATURE", "0"))

    api_key = os.getenv("OPENAI_API_KEY")
    if is_local_compatible:
        api_key = api_key or "local-dev-key"
    elif not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI cloud response formatting mode.")

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

    def _llm_callable(system_prompt: str, user_prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content if response.choices else ""
        return content or ""

    return _llm_callable


def _load_datasets() -> dict[str, pd.DataFrame]:
    """Load processed CSVs required by deterministic executor."""
    metrics_path = PROCESSED_DIR / "metrics_long.csv"
    orders_path = PROCESSED_DIR / "orders_long.csv"

    if not metrics_path.exists() or not orders_path.exists():
        raise RuntimeError(
            "Missing processed datasets. Expected: "
            f"'{metrics_path}' and '{orders_path}'. Run scripts/prepare_data.py first."
        )

    return {
        "metrics_long": pd.read_csv(metrics_path),
        "orders_long": pd.read_csv(orders_path),
    }


app = FastAPI(title="Rappi Ops AI", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    """Warm-load datasets and LLM callable once."""
    app.state.datasets = _load_datasets()
    app.state.llm_callable = _build_formatter_llm_callable()


@app.get("/api/health")
def health() -> dict[str, str]:
    """Simple health endpoint for UI boot checks."""
    return {"status": "ok"}


@app.post("/api/chat/query")
def chat_query(payload: QueryRequest) -> dict[str, Any]:
    """Run full deterministic line: parse -> normalize -> validate -> execute -> format."""
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty.")

    steps: list[dict[str, Any]] = []
    started = time.perf_counter()

    try:
        t0 = time.perf_counter()
        parsed = parse_question_to_json(question, payload.conversation_context)
        steps.append(
            {
                "id": "parse",
                "title": "Parse Question",
                "status": "completed",
                "duration_s": round(time.perf_counter() - t0, 3),
                "detail": parsed,
            }
        )

        t1 = time.perf_counter()
        normalized = normalize_parsed_payload(parsed)
        steps.append(
            {
                "id": "normalize",
                "title": "Normalize Query",
                "status": "completed",
                "duration_s": round(time.perf_counter() - t1, 3),
                "detail": normalized,
            }
        )

        t2 = time.perf_counter()
        validated = validate_parsed_query(parsed)
        validated_dump = validated.model_dump(mode="json")
        steps.append(
            {
                "id": "validate",
                "title": "Validate Query",
                "status": "completed",
                "duration_s": round(time.perf_counter() - t2, 3),
                "detail": validated_dump,
            }
        )

        t3 = time.perf_counter()
        execution_result = execute_query(validated, app.state.datasets)
        steps.append(
            {
                "id": "execute",
                "title": "Execute Analytics",
                "status": "completed",
                "duration_s": round(time.perf_counter() - t3, 3),
                "detail": {
                    "title": execution_result.get("title"),
                    "row_count": len(execution_result.get("rows") or []),
                    "metadata": execution_result.get("metadata") or {},
                },
            }
        )

        t4 = time.perf_counter()
        answer = format_response_with_llm(
            question=question,
            execution_result=execution_result,
            llm_callable=app.state.llm_callable,
        )
        steps.append(
            {
                "id": "format",
                "title": "Format Response",
                "status": "completed",
                "duration_s": round(time.perf_counter() - t4, 3),
                "detail": {"answer_preview": answer[:220]},
            }
        )

        return {
            "question": question,
            "answer": answer,
            "parsed_payload": parsed,
            "normalized_payload": normalized,
            "validated_query": validated_dump,
            "execution_result": execution_result,
            "pipeline": steps,
            "total_duration_s": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        return JSONResponse(
            status_code=422,
            content={
                "question": question,
                "error": str(exc),
                "pipeline": steps,
                "total_duration_s": round(time.perf_counter() - started, 3),
            },
        )


@app.post("/api/insights/report/generate")
def generate_insights_report(payload: InsightsReportRequest) -> dict[str, Any]:
    """Generate report markdown and return render-ready payload."""
    started = time.perf_counter()
    try:
        result = generate_and_save_insights_report(
            datasets=app.state.datasets,
            output_path=DEFAULT_REPORT_PATH,
            top_k_critical=payload.top_k_critical,
            force_fallback=payload.force_fallback,
        )
        return {
            "markdown": result["markdown"],
            "output_path": result["output_path"],
            "download_url": "/api/insights/report/download",
            "insight_count": result["insight_count"],
            "top_critical_titles": result["top_critical_titles"],
            "generated_at": result["generated_at"],
            "duration_s": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/insights/report/download")
def download_insights_report() -> FileResponse:
    """Download latest generated insights markdown report."""
    if not DEFAULT_REPORT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="Insights report not found. Generate it first from /api/insights/report/generate.",
        )
    return FileResponse(
        path=DEFAULT_REPORT_PATH,
        media_type="text/markdown",
        filename="insights_report.md",
    )


if FRONTEND_DIST.exists():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str) -> FileResponse:
        """Serve built frontend as SPA fallback."""
        target = FRONTEND_DIST / full_path
        if full_path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
else:
    @app.get("/")
    def frontend_not_built() -> dict[str, str]:
        """Helpful message when frontend build is missing."""
        return {
            "message": "Frontend build not found. Run 'cd frontend && npm install && npm run build'."
        }
