"""
app/analysis/__init__.py — Orchestrator that runs all 5 checks for one image.

Design
------
Each check is wrapped in its own try/except so a failure in one check
(e.g. Tesseract binary missing) does NOT prevent the other checks from running
and being recorded.  The worker collects all results regardless of individual
failures, then writes them as AnalysisResult rows in a single DB transaction.

Return value
------------
Returns a list of dicts, each matching the AnalysisResult schema:
  {
    "check_name": str,
    "passed": bool,
    "score": float,
    "details": dict,
    "error": str | None,   # only present if the check itself raised
  }
"""
from __future__ import annotations

import logging
from typing import Any

from app.analysis.blur import detect_blur
from app.analysis.brightness import detect_brightness
from app.analysis.duplicate import detect_duplicate, compute_phash
from app.analysis.screenshot import detect_screenshot
from app.analysis.plate_ocr import detect_plate

logger = logging.getLogger(__name__)


def run_all_checks(
    image_bytes: bytes,
    existing_hashes: list[str],
) -> tuple[list[dict[str, Any]], str | None]:
    """
    Run all 5 analysis checks and return (results, computed_phash).

    Parameters
    ----------
    image_bytes    : raw bytes of the uploaded image
    existing_hashes: pHash strings of all previously-completed images (for duplicate check)

    Returns
    -------
    results        : list of result dicts (one per check)
    computed_hash  : pHash string of the current image, or None if hashing failed
    """
    results: list[dict[str, Any]] = []
    computed_hash: str | None = None

    # ── 1. Blur ──────────────────────────────────────────────────────────────
    try:
        blur_result = detect_blur(image_bytes)
        results.append({"check_name": "blur", **blur_result})
        logger.info("blur check: passed=%s score=%.3f", blur_result["passed"], blur_result["score"])
    except Exception as exc:
        logger.error("blur check failed with exception: %s", exc, exc_info=True)
        results.append({
            "check_name": "blur",
            "passed": False,
            "score": 0.0,
            "details": {"error": str(exc), "verdict": "check_error"},
        })

    # ── 2. Brightness ────────────────────────────────────────────────────────
    try:
        brightness_result = detect_brightness(image_bytes)
        results.append({"check_name": "brightness", **brightness_result})
        logger.info("brightness check: passed=%s score=%.3f", brightness_result["passed"], brightness_result["score"])
    except Exception as exc:
        logger.error("brightness check failed with exception: %s", exc, exc_info=True)
        results.append({
            "check_name": "brightness",
            "passed": False,
            "score": 0.0,
            "details": {"error": str(exc), "verdict": "check_error"},
        })

    # ── 3. Duplicate ─────────────────────────────────────────────────────────
    try:
        # Compute hash first (needed to store on Image row)
        computed_hash = compute_phash(image_bytes)
        dup_result = detect_duplicate(image_bytes, existing_hashes)
        results.append({"check_name": "duplicate", **dup_result})
        logger.info("duplicate check: passed=%s score=%.3f", dup_result["passed"], dup_result["score"])
    except Exception as exc:
        logger.error("duplicate check failed with exception: %s", exc, exc_info=True)
        results.append({
            "check_name": "duplicate",
            "passed": False,
            "score": 0.0,
            "details": {"error": str(exc), "verdict": "check_error"},
        })

    # ── 4. Screenshot ────────────────────────────────────────────────────────
    try:
        screenshot_result = detect_screenshot(image_bytes)
        results.append({"check_name": "screenshot", **screenshot_result})
        logger.info("screenshot check: passed=%s score=%.3f", screenshot_result["passed"], screenshot_result["score"])
    except Exception as exc:
        logger.error("screenshot check failed with exception: %s", exc, exc_info=True)
        results.append({
            "check_name": "screenshot",
            "passed": False,
            "score": 0.0,
            "details": {"error": str(exc), "verdict": "check_error"},
        })

    # ── 5. Plate OCR ─────────────────────────────────────────────────────────
    try:
        plate_result = detect_plate(image_bytes)
        results.append({"check_name": "plate_ocr", **plate_result})
        logger.info("plate_ocr check: passed=%s score=%.3f", plate_result["passed"], plate_result["score"])
    except Exception as exc:
        logger.error("plate_ocr check failed with exception: %s", exc, exc_info=True)
        results.append({
            "check_name": "plate_ocr",
            "passed": False,
            "score": 0.0,
            "details": {"error": str(exc), "verdict": "check_error"},
        })

    return results, computed_hash
