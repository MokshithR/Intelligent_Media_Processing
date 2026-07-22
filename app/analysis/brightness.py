"""
app/analysis/brightness.py — Brightness / exposure detection.

Algorithm
---------
Convert to grayscale, compute the mean pixel intensity (0–255).
Two thresholds define the acceptable exposure window:

  - < 40  → too dark / under-exposed
  - > 220 → too bright / over-exposed (blown out)

Thresholds chosen after testing on vehicle images taken in poor lighting
and in direct sunlight — values outside this range were consistently
unusable for licence-plate reading or damage assessment.

Score interpretation (0.0–1.0):
  Distance from the centre of the ideal band (mean=130), normalised so
  that a perfectly centred image scores 1.0 and an image at the boundary
  (40 or 220) scores ~0.5.  Outside the boundaries score < 0.5.
  `passed` is True when mean is in [40, 220].
"""
from __future__ import annotations

import cv2
import numpy as np

# ── Configurable thresholds ─────────────────────────────────────────────────
DARK_THRESHOLD = 40
BRIGHT_THRESHOLD = 220
IDEAL_MEAN = 130.0  # midpoint of the acceptable band


def detect_brightness(image_bytes: bytes) -> dict:
    """
    Analyse exposure of raw image bytes.

    Returns passed, score (0–1), details.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("cv2.imdecode returned None — image bytes may be corrupt")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean_intensity = float(gray.mean())

    passed = DARK_THRESHOLD <= mean_intensity <= BRIGHT_THRESHOLD

    # Normalise: 1.0 at IDEAL_MEAN, decays to 0 at the edges (0 and 255)
    deviation = abs(mean_intensity - IDEAL_MEAN)
    max_deviation = max(IDEAL_MEAN - 0, 255 - IDEAL_MEAN)  # ~130
    score = max(0.0, 1.0 - deviation / max_deviation)

    if mean_intensity < DARK_THRESHOLD:
        verdict = "too_dark"
    elif mean_intensity > BRIGHT_THRESHOLD:
        verdict = "too_bright"
    else:
        verdict = "ok"

    return {
        "passed": passed,
        "score": round(score, 4),
        "details": {
            "mean_intensity": round(mean_intensity, 2),
            "dark_threshold": DARK_THRESHOLD,
            "bright_threshold": BRIGHT_THRESHOLD,
            "verdict": verdict,
        },
    }
