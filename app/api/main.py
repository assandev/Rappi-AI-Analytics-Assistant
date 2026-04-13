"""FastAPI app that serves analytics API and built frontend in one process."""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from app.services.execution import execute_query
from app.services.query_parser import parse_question_to_json
from app.services.query_validator import normalize_parsed_payload, validate_parsed_query
from src.conversation import (
    ConversationState,
    build_contextual_parser_input,
    is_follow_up_question,
)
from src.insights.service import (
    DEFAULT_REPORT_PATH,
    generate_and_save_insights_report,
    send_insights_report_email,
)
from src.response.response_formatter import format_response_with_llm


load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
logger = logging.getLogger("uvicorn.error")


class QueryRequest(BaseModel):
    """HTTP input payload for chatbot execution."""

    question: str = Field(min_length=1)
    conversation_context: dict[str, Any] | None = None


class InsightsReportRequest(BaseModel):
    """HTTP input payload for one-click insights report generation."""

    top_k_critical: int = Field(default=5, ge=3, le=5)
    force_fallback: bool = False


class InsightsReportEmailRequest(BaseModel):
    """HTTP input payload for sending report by email."""

    recipient_email: str = Field(min_length=3)


def _new_request_id() -> str:
    """Generate short request identifier for logs and tracing."""
    return uuid.uuid4().hex[:8]


def _question_preview(question: str, max_len: int = 96) -> str:
    """Return compact single-line preview for logs."""
    compact = " ".join(question.strip().split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len]}..."


def _mask_email(email: str) -> str:
    """Mask email user-part for safer logs."""
    value = (email or "").strip()
    if "@" not in value:
        return "***"
    user, domain = value.split("@", 1)
    if len(user) <= 2:
        masked_user = f"{user[:1]}***"
    else:
        masked_user = f"{user[:2]}***"
    return f"{masked_user}@{domain}"


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
    app.state.conversation_state = ConversationState()
    metrics_rows = len(app.state.datasets["metrics_long"])
    orders_rows = len(app.state.datasets["orders_long"])
    logger.info(
        "[startup] datasets loaded metrics_rows=%s orders_rows=%s",
        metrics_rows,
        orders_rows,
    )
    logger.info("[startup] conversation state initialized")
    logger.info("[startup] frontend_dist_exists=%s", FRONTEND_DIST.exists())


@app.middleware("http")
async def log_api_requests(request: Request, call_next):
    """Emit meaningful request lifecycle logs for API endpoints."""
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    request_id = _new_request_id()
    request.state.request_id = request_id
    started = time.perf_counter()
    logger.info("[req:%s] %s %s started", request_id, request.method, request.url.path)

    try:
        response = await call_next(request)
    except Exception:
        duration_s = time.perf_counter() - started
        logger.exception(
            "[req:%s] %s %s failed duration_s=%.3f",
            request_id,
            request.method,
            request.url.path,
            duration_s,
        )
        raise

    duration_s = time.perf_counter() - started
    logger.info(
        "[req:%s] %s %s completed status=%s duration_s=%.3f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_s,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/api/health")
def health(request: Request) -> dict[str, str]:
    """Simple health endpoint for UI boot checks."""
    request_id = getattr(request.state, "request_id", _new_request_id())
    logger.info("[req:%s][health] status=ok", request_id)
    return {"status": "ok"}


@app.post("/api/chat/query")
def chat_query(payload: QueryRequest, request: Request) -> dict[str, Any]:
    """Run full deterministic line: parse -> normalize -> validate -> execute -> format."""
    request_id = getattr(request.state, "request_id", _new_request_id())
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty.")
    logger.info("[req:%s][chat.query] question=%s", request_id, _question_preview(question))

    state: ConversationState = getattr(app.state, "conversation_state", ConversationState())
    app.state.conversation_state = state

    follow_up_detected = is_follow_up_question(question)
    parser_input = build_contextual_parser_input(question, state)
    contextual_parser_input_used = parser_input != question
    contextual_parse_fallback_used = False
    logger.info(
        "[req:%s][chat.query] follow_up_detected=%s contextual_parser_input_used=%s",
        request_id,
        follow_up_detected,
        contextual_parser_input_used,
    )

    steps: list[dict[str, Any]] = []
    started = time.perf_counter()

    try:
        t0 = time.perf_counter()
        try:
            parsed = parse_question_to_json(parser_input, payload.conversation_context)
        except Exception:
            if not contextual_parser_input_used:
                raise
            parsed = parse_question_to_json(question, payload.conversation_context)
            contextual_parse_fallback_used = True
            logger.warning(
                "[req:%s][chat.query] contextual parse failed, fallback to raw question",
                request_id,
            )

        parser_input_preview = parser_input if len(parser_input) <= 300 else f"{parser_input[:300]}..."
        logger.info(
            "[req:%s][chat.query] parsed_intent=%s metric=%s",
            request_id,
            parsed.get("intent"),
            parsed.get("metric"),
        )
        steps.append(
            {
                "id": "parse",
                "title": "Parse Question",
                "status": "completed",
                "duration_s": round(time.perf_counter() - t0, 3),
                "detail": {
                    "parsed_payload": parsed,
                    "follow_up_detected": follow_up_detected,
                    "contextual_parser_input_used": contextual_parser_input_used,
                    "contextual_parse_fallback_used": contextual_parse_fallback_used,
                    "parser_input_preview": parser_input_preview,
                },
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
        validated = validate_parsed_query(normalized)
        validated_dump = validated.model_dump(mode="json")
        logger.info(
            "[req:%s][chat.query] validated_intent=%s group_by=%s",
            request_id,
            validated_dump.get("intent"),
            validated_dump.get("group_by"),
        )
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
        row_count = len(execution_result.get("rows") or [])
        logger.info(
            "[req:%s][chat.query] execution_done title=%s row_count=%s",
            request_id,
            execution_result.get("title"),
            row_count,
        )
        steps.append(
            {
                "id": "execute",
                "title": "Execute Analytics",
                "status": "completed",
                "duration_s": round(time.perf_counter() - t3, 3),
                "detail": {
                    "title": execution_result.get("title"),
                    "row_count": row_count,
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
        logger.info(
            "[req:%s][chat.query] formatter_done answer_chars=%s",
            request_id,
            len(answer),
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

        state.last_user_question = question
        state.last_validated_query = validated_dump
        state.last_execution_result = execution_result
        logger.info(
            "[req:%s][chat.query] memory_updated intent=%s total_duration_s=%.3f",
            request_id,
            validated_dump.get("intent"),
            time.perf_counter() - started,
        )

        return {
            "question": question,
            "answer": answer,
            "follow_up_detected": follow_up_detected,
            "contextual_parser_input_used": contextual_parser_input_used,
            "contextual_parse_fallback_used": contextual_parse_fallback_used,
            "parsed_payload": parsed,
            "normalized_payload": normalized,
            "validated_query": validated_dump,
            "execution_result": execution_result,
            "pipeline": steps,
            "total_duration_s": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        logger.exception("[req:%s][chat.query] failed error=%s", request_id, exc)
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
def generate_insights_report(payload: InsightsReportRequest, request: Request) -> dict[str, Any]:
    """Generate report markdown and return render-ready payload."""
    request_id = getattr(request.state, "request_id", _new_request_id())
    started = time.perf_counter()
    logger.info(
        "[req:%s][insights.generate] started top_k_critical=%s force_fallback=%s",
        request_id,
        payload.top_k_critical,
        payload.force_fallback,
    )
    try:
        result = generate_and_save_insights_report(
            datasets=app.state.datasets,
            output_path=DEFAULT_REPORT_PATH,
            top_k_critical=payload.top_k_critical,
            force_fallback=payload.force_fallback,
        )
        logger.info(
            "[req:%s][insights.generate] done insight_count=%s output_path=%s duration_s=%.3f",
            request_id,
            result["insight_count"],
            result["output_path"],
            time.perf_counter() - started,
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
        logger.exception("[req:%s][insights.generate] failed error=%s", request_id, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/insights/report/download")
def download_insights_report(request: Request) -> FileResponse:
    """Download latest generated insights markdown report."""
    request_id = getattr(request.state, "request_id", _new_request_id())
    if not DEFAULT_REPORT_PATH.exists():
        logger.warning("[req:%s][insights.download] report_not_found", request_id)
        raise HTTPException(
            status_code=404,
            detail="Insights report not found. Generate it first from /api/insights/report/generate.",
        )
    logger.info("[req:%s][insights.download] serving path=%s", request_id, DEFAULT_REPORT_PATH)
    return FileResponse(
        path=DEFAULT_REPORT_PATH,
        media_type="text/markdown",
        filename="insights_report.md",
    )


@app.post("/api/insights/report/email")
def email_insights_report(payload: InsightsReportEmailRequest, request: Request) -> dict[str, Any]:
    """Send latest insights report to recipient with fixed subject and body."""
    request_id = getattr(request.state, "request_id", _new_request_id())
    started = time.perf_counter()
    logger.info(
        "[req:%s][insights.email] started recipient=%s",
        request_id,
        _mask_email(payload.recipient_email),
    )
    try:
        result = send_insights_report_email(
            recipient_email=payload.recipient_email,
            report_path=DEFAULT_REPORT_PATH,
        )
        logger.info(
            "[req:%s][insights.email] sent recipient=%s attachment=%s duration_s=%.3f",
            request_id,
            _mask_email(result["recipient_email"]),
            result["attachment_name"],
            time.perf_counter() - started,
        )
        return {
            "message": "Insights report email sent successfully.",
            "recipient_email": result["recipient_email"],
            "subject": result["subject"],
            "attachment_name": result["attachment_name"],
            "duration_s": round(time.perf_counter() - started, 3),
        }
    except FileNotFoundError as exc:
        logger.warning("[req:%s][insights.email] report_not_found error=%s", request_id, exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("[req:%s][insights.email] failed error=%s", request_id, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
