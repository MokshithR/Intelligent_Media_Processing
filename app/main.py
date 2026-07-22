"""
app/main.py — FastAPI application factory and route registration.

The OpenAPI docs are intentionally kept enabled (they are a deliverable per spec).
Structured logging is configured here so all modules share the same format.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.routes.upload import router as upload_router
from app.routes.results import router as results_router

# ── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── App factory ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Intelligent Media Processing Pipeline",
    description=(
        "Async vehicle image analysis system. Upload an image, get back quality "
        "and authenticity checks: blur detection, brightness analysis, duplicate "
        "detection, screenshot heuristic, and Indian vehicle plate OCR.\n\n"
        "**Dashboard**: [`/ui`](/ui)"
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow all origins for demo purposes (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Route registration ───────────────────────────────────────────────────────
app.include_router(upload_router, tags=["Images"])
app.include_router(results_router)


# ── Root redirect → dashboard ────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect the root URL to the Intake dashboard."""
    return RedirectResponse(url="/ui")


# ── Static dashboard ─────────────────────────────────────────────────────────
_static_dir = Path(__file__).parent / "static"
if _static_dir.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_static_dir), html=True), name="ui")
    logger.info("Dashboard mounted at /ui")
else:
    logger.warning("app/static/ not found — dashboard will not be served")

logger.info("FastAPI application started — docs at /docs | dashboard at /ui")
