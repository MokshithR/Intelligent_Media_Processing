"""
app/analysis/plate_ocr.py — Vehicle licence plate OCR + format validation.

Process
-------
1. Run Tesseract on the full image (PSEM 11 — sparse text detection, which
   works better for plates embedded in scene photos than the default block mode).
2. Normalise extracted text: uppercase, strip whitespace and non-alphanumeric
   characters other than spaces.
3. Regex-match each token against the standard Indian vehicle registration
   format: AA 00 AA 0000  (state code + RTO code + series + number).

Indian plate regex: ^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$
   ↳ Allows both old (2-digit RTO) and new (1-digit RTO) formats.
   ↳ Series letters: 1 or 2 chars.
   ↳ Sequence number: exactly 4 digits.
   ↳ Whitespace stripped before matching so "MH 12 AB 1234" → "MH12AB1234".

Score interpretation (0.0–1.0):
  1.0 → valid Indian plate found
  0.5 → text extracted but no plate-like token found
  0.0 → OCR returned no text at all
`passed` = True when a valid plate is detected.

Assumption: single Indian plate format. Other country formats are not checked.
"""
from __future__ import annotations

import re
import logging

import pytesseract
import numpy as np
import cv2

logger = logging.getLogger(__name__)

# ── Configurable ─────────────────────────────────────────────────────────────
# Standard Indian vehicle registration plate pattern
PLATE_PATTERN = re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$")


def _preprocess_for_ocr(img_bgr: np.ndarray) -> np.ndarray:
    """
    Light preprocessing to improve OCR accuracy:
    - Convert to grayscale
    - Apply mild threshold (Otsu) to binarise text
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def _find_plate_tokens(raw_text: str) -> list[str]:
    """
    From raw OCR text, extract candidate plate strings:
    - Uppercase, strip spaces within each candidate token
    - Check each against PLATE_PATTERN
    """
    # Split on whitespace/newlines, recombine pairs of adjacent tokens
    tokens_raw = raw_text.upper().split()
    candidates: list[str] = []

    # Try each single token
    for tok in tokens_raw:
        cleaned = re.sub(r"[^A-Z0-9]", "", tok)
        if cleaned:
            candidates.append(cleaned)

    # Try pairs of adjacent tokens (for plates split by a space in OCR)
    for i in range(len(tokens_raw) - 1):
        joined = re.sub(r"[^A-Z0-9]", "", tokens_raw[i] + tokens_raw[i + 1])
        if joined:
            candidates.append(joined)

    return candidates


def detect_plate(image_bytes: bytes) -> dict:
    """
    Run OCR on image bytes and validate against Indian plate format.

    Returns passed, score (0–1), details.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("cv2.imdecode returned None — image may be corrupt")

    processed = _preprocess_for_ocr(img)

    # PSM 11: sparse text — good for embedded text in scene photos
    try:
        raw_text = pytesseract.image_to_string(
            processed,
            config="--psm 11 --oem 3",
        )
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract binary not found — ensure tesseract-ocr is installed")
        raise

    raw_text = raw_text.strip()
    candidates = _find_plate_tokens(raw_text)

    matched_plate: str | None = None
    for candidate in candidates:
        if PLATE_PATTERN.match(candidate):
            matched_plate = candidate
            break

    if not raw_text:
        score = 0.0
        verdict = "no_text_extracted"
    elif matched_plate:
        score = 1.0
        verdict = "plate_found"
    else:
        score = 0.5
        verdict = "text_found_no_plate_match"

    passed = matched_plate is not None

    return {
        "passed": passed,
        "score": score,
        "details": {
            "matched_plate": matched_plate,
            "raw_ocr_text": raw_text[:500],   # truncate very long OCR output
            "candidates_checked": candidates[:20],
            "plate_regex": PLATE_PATTERN.pattern,
            "verdict": verdict,
            "assumption": "Indian vehicle registration format only (e.g. MH12AB1234).",
        },
    }
