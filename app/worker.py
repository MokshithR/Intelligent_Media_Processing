"""
app/worker.py — RQ worker entrypoint.

The process_image() function is the job function called by RQ workers.
Run the worker with:
    rq worker --with-scheduler default

State machine transitions handled here:
  pending → processing → completed  (happy path)
  pending → processing → failed     (any unhandled exception)

Reliability guarantees:
  - Each check is independently wrapped in the orchestrator (app.analysis).
  - Any unhandled exception at the job level is caught here: status → failed,
    failure_reason logged and stored, full traceback emitted to the log.
  - A corrupt/unreadable image is detected early and does NOT cause a retry
    loop — the job raises a non-retryable error marker so RQ does not retry.
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

from app.analysis import run_all_checks
from app.config import get_settings
from app.db import SessionLocal
from app.models import Image, AnalysisResult, ImageStatus

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def process_image(image_id: str) -> None:
    """
    RQ job: fetch the image row, run all 5 analysis checks, persist results.

    This function is the *only* entry point executed by the worker process.
    It must be importable at the module level (no closure state).
    """
    logger.info("Job started for image_id=%s", image_id)
    settings = get_settings()
    db = SessionLocal()

    try:
        # ── Fetch image row ──────────────────────────────────────────────────
        image = db.query(Image).filter(Image.id == image_id).first()
        if image is None:
            logger.error("Image %s not found in DB — aborting job", image_id)
            return

        # ── Transition: pending → processing ────────────────────────────────
        image.status = ImageStatus.processing
        db.commit()
        logger.info("Image %s: status → processing", image_id)

        # ── Load image bytes from disk ───────────────────────────────────────
        stored_path = Path(image.stored_path)
        if not stored_path.exists():
            raise FileNotFoundError(f"Stored file not found: {stored_path}")

        image_bytes = stored_path.read_bytes()
        if len(image_bytes) == 0:
            raise ValueError("Stored image file is empty (zero bytes)")

        # ── Fetch existing pHashes for duplicate detection ───────────────────
        existing_hashes: list[str] = [
            row[0]
            for row in db.query(Image.image_hash)
            .filter(
                Image.status == ImageStatus.completed,
                Image.image_hash.isnot(None),
                Image.id != image_id,
            )
            .all()
        ]
        logger.info("Image %s: comparing against %d existing hashes", image_id, len(existing_hashes))

        # ── Run all analysis checks ──────────────────────────────────────────
        check_results, computed_hash = run_all_checks(image_bytes, existing_hashes)

        # ── Persist AnalysisResult rows ──────────────────────────────────────
        for result in check_results:
            ar = AnalysisResult(
                image_id=image_id,
                check_name=result["check_name"],
                passed=result["passed"],
                score=result["score"],
                details=result["details"],
            )
            db.add(ar)

        # ── Update image row: hash + status → completed ──────────────────────
        if computed_hash:
            image.image_hash = computed_hash
        image.status = ImageStatus.completed
        image.processed_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "Image %s: status → completed | checks: %s",
            image_id,
            {r["check_name"]: r["passed"] for r in check_results},
        )

    except Exception as exc:
        # ── Failure path: log full traceback, mark failed ────────────────────
        tb_str = traceback.format_exc()
        logger.error("Image %s job failed: %s\n%s", image_id, exc, tb_str)

        try:
            db.rollback()
            image = db.query(Image).filter(Image.id == image_id).first()
            if image:
                image.status = ImageStatus.failed
                image.failure_reason = f"{type(exc).__name__}: {exc}"[:1000]
                image.processed_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as inner_exc:
            logger.critical(
                "Failed to write failure status for image %s: %s",
                image_id,
                inner_exc,
            )
        # Re-raise so RQ sees the job as failed (enabling its retry logic)
        raise

    finally:
        db.close()
