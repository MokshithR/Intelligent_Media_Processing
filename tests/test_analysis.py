"""
tests/test_analysis.py — Unit tests for all 5 analysis checks.

All tests use synthesized PIL images (no external files required).
Tesseract-dependent tests are conditionally skipped if tesseract binary
is not available in the test environment.
"""
from __future__ import annotations

import io
import shutil
import pytest

from tests.conftest import (
    make_sharp_image_bytes,
    make_blurry_image_bytes,
    make_dark_image_bytes,
    make_bright_image_bytes,
    make_normal_image_bytes,
    make_16_9_image_bytes,
)


# ─── Blur detection ────────────────────────────────────────────────────────────

class TestBlurDetection:
    def test_sharp_image_passes(self, sharp_image):
        from app.analysis.blur import detect_blur
        result = detect_blur(sharp_image)
        assert result["passed"] is True
        assert result["score"] > 0.0
        assert result["details"]["verdict"] == "sharp"
        assert "laplacian_variance" in result["details"]

    def test_blurry_image_fails(self, blurry_image):
        from app.analysis.blur import detect_blur
        result = detect_blur(blurry_image)
        assert result["passed"] is False
        assert result["score"] < 0.5
        assert result["details"]["verdict"] == "blurry"

    def test_score_in_range(self, sharp_image):
        from app.analysis.blur import detect_blur
        result = detect_blur(sharp_image)
        assert 0.0 <= result["score"] <= 1.0

    def test_corrupt_bytes_raise(self):
        from app.analysis.blur import detect_blur
        with pytest.raises(ValueError, match="cv2.imdecode"):
            detect_blur(b"not an image at all")

    def test_details_has_threshold(self, normal_image):
        from app.analysis.blur import detect_blur, BLUR_THRESHOLD
        result = detect_blur(normal_image)
        assert result["details"]["threshold"] == BLUR_THRESHOLD


# ─── Brightness detection ──────────────────────────────────────────────────────

class TestBrightnessDetection:
    def test_dark_image_fails(self, dark_image):
        from app.analysis.brightness import detect_brightness
        result = detect_brightness(dark_image)
        assert result["passed"] is False
        assert result["details"]["verdict"] == "too_dark"

    def test_bright_image_fails(self, bright_image):
        from app.analysis.brightness import detect_brightness
        result = detect_brightness(bright_image)
        assert result["passed"] is False
        assert result["details"]["verdict"] == "too_bright"

    def test_normal_image_passes(self, normal_image):
        from app.analysis.brightness import detect_brightness
        result = detect_brightness(normal_image)
        assert result["passed"] is True
        assert result["details"]["verdict"] == "ok"

    def test_score_in_range(self, dark_image, bright_image, normal_image):
        from app.analysis.brightness import detect_brightness
        for img_bytes in (dark_image, bright_image, normal_image):
            result = detect_brightness(img_bytes)
            assert 0.0 <= result["score"] <= 1.0

    def test_details_has_thresholds(self, normal_image):
        from app.analysis.brightness import detect_brightness, DARK_THRESHOLD, BRIGHT_THRESHOLD
        result = detect_brightness(normal_image)
        assert result["details"]["dark_threshold"] == DARK_THRESHOLD
        assert result["details"]["bright_threshold"] == BRIGHT_THRESHOLD


# ─── Duplicate detection ───────────────────────────────────────────────────────

class TestDuplicateDetection:
    def test_unique_image_passes(self, sharp_image):
        from app.analysis.duplicate import detect_duplicate
        result = detect_duplicate(sharp_image, [])
        assert result["passed"] is True
        assert result["score"] > 0.0

    def test_exact_duplicate_fails(self, sharp_image):
        from app.analysis.duplicate import detect_duplicate, compute_phash
        existing_hash = compute_phash(sharp_image)
        result = detect_duplicate(sharp_image, [existing_hash])
        assert result["passed"] is False
        assert result["details"]["hamming_distance"] == 0
        assert result["details"]["verdict"] == "duplicate"

    def test_different_images_unique(self, sharp_image, dark_image):
        from app.analysis.duplicate import detect_duplicate, compute_phash
        existing_hash = compute_phash(dark_image)
        result = detect_duplicate(sharp_image, [existing_hash])
        # These images are very different, should not be flagged
        assert result["passed"] is True

    def test_compute_phash_returns_string(self, normal_image):
        from app.analysis.duplicate import compute_phash
        h = compute_phash(normal_image)
        assert isinstance(h, str)
        assert len(h) > 0

    def test_score_decreases_with_similarity(self, sharp_image):
        from app.analysis.duplicate import detect_duplicate, compute_phash
        h = compute_phash(sharp_image)
        same_result = detect_duplicate(sharp_image, [h])
        diff_result = detect_duplicate(sharp_image, [])
        assert same_result["score"] < diff_result["score"]

    def test_malformed_hash_skipped_gracefully(self, sharp_image):
        from app.analysis.duplicate import detect_duplicate
        # Should not raise; malformed hash is skipped
        result = detect_duplicate(sharp_image, ["not_a_valid_hash", "also_bad"])
        assert "error" not in result


# ─── Screenshot detection ──────────────────────────────────────────────────────

class TestScreenshotDetection:
    def test_no_exif_screen_ratio_fails(self, screen_ratio_image):
        """16:9 image with no EXIF → 2 signals, score=0.0, fails."""
        from app.analysis.screenshot import detect_screenshot
        result = detect_screenshot(screen_ratio_image)
        # Synthesized JPEG has no EXIF and 16:9 ratio → both signals fire
        assert result["details"]["signals_fired"] == 2
        assert result["passed"] is False
        assert result["score"] == 0.0

    def test_details_has_disclaimer(self, normal_image):
        from app.analysis.screenshot import detect_screenshot
        result = detect_screenshot(normal_image)
        assert "disclaimer" in result["details"]
        assert "heuristic" in result["details"]["disclaimer"].lower()

    def test_score_in_range(self, screen_ratio_image, normal_image):
        from app.analysis.screenshot import detect_screenshot
        for img_bytes in (screen_ratio_image, normal_image):
            result = detect_screenshot(img_bytes)
            assert 0.0 <= result["score"] <= 1.0

    def test_result_structure(self, normal_image):
        from app.analysis.screenshot import detect_screenshot
        result = detect_screenshot(normal_image)
        assert "passed" in result
        assert "score" in result
        assert "details" in result
        assert "has_camera_exif" in result["details"]
        assert "image_dimensions" in result["details"]


# ─── Plate OCR ─────────────────────────────────────────────────────────────────

TESSERACT_AVAILABLE = shutil.which("tesseract") is not None


class TestPlateOCR:
    def test_plate_regex_valid_formats(self):
        """Validate the regex matches expected Indian plate formats."""
        import re
        from app.analysis.plate_ocr import PLATE_PATTERN
        valid_plates = ["MH12AB1234", "DL4CA1234", "KA09AB1234", "TN01Z1234"]
        for plate in valid_plates:
            assert PLATE_PATTERN.match(plate), f"Expected {plate} to match"

    def test_plate_regex_invalid_formats(self):
        import re
        from app.analysis.plate_ocr import PLATE_PATTERN
        invalid = ["12MH1234", "MHAB1234", "MH12AB12", "ABC123"]
        for plate in invalid:
            assert not PLATE_PATTERN.match(plate), f"Expected {plate} to NOT match"

    @pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="tesseract not installed")
    def test_no_plate_in_plain_image(self, normal_image):
        from app.analysis.plate_ocr import detect_plate
        result = detect_plate(normal_image)
        # Plain grey image — no plate text expected
        assert result["passed"] is False
        assert result["details"]["matched_plate"] is None
        assert result["score"] in (0.0, 0.5)

    @pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="tesseract not installed")
    def test_image_with_plate_text(self):
        """Create a synthetic image with plate text drawn on it."""
        from PIL import Image as PILImage, ImageDraw, ImageFont
        import io
        from app.analysis.plate_ocr import detect_plate

        img = PILImage.new("RGB", (400, 100), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        # Draw text that looks like a plate; OCR may or may not catch it perfectly
        draw.text((10, 30), "MH12AB1234", fill=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        result = detect_plate(image_bytes)
        # The test is lenient — we just verify no exception and correct structure
        assert "passed" in result
        assert "score" in result
        assert "details" in result
        assert 0.0 <= result["score"] <= 1.0

    def test_corrupt_bytes_raise(self):
        from app.analysis.plate_ocr import detect_plate
        with pytest.raises(ValueError, match="cv2.imdecode"):
            detect_plate(b"garbage bytes")


# ─── Orchestrator ──────────────────────────────────────────────────────────────

class TestOrchestrator:
    @pytest.mark.skipif(not TESSERACT_AVAILABLE, reason="tesseract not installed")
    def test_all_checks_run(self, normal_image):
        from app.analysis import run_all_checks
        results, computed_hash = run_all_checks(normal_image, [])
        check_names = [r["check_name"] for r in results]
        assert "blur" in check_names
        assert "brightness" in check_names
        assert "duplicate" in check_names
        assert "screenshot" in check_names
        assert "plate_ocr" in check_names
        assert len(results) == 5

    def test_partial_results_on_check_error(self, normal_image, monkeypatch):
        """If one check raises, others should still return results.
        
        Plate OCR is also mocked to avoid requiring Tesseract in CI.
        """
        import app.analysis as orchestrator

        # Make the blur check always raise
        def bad_blur(image_bytes):
            raise RuntimeError("Simulated blur failure")

        # Mock plate OCR to avoid Tesseract dependency in this test
        def mock_plate(image_bytes):
            return {"passed": False, "score": 0.5, "details": {"verdict": "mocked"}}

        monkeypatch.setattr(orchestrator, "detect_blur", bad_blur)
        monkeypatch.setattr(orchestrator, "detect_plate", mock_plate)

        results, _ = orchestrator.run_all_checks(normal_image, [])
        blur_result = next(r for r in results if r["check_name"] == "blur")
        assert blur_result["passed"] is False
        assert "error" in blur_result["details"]
        # Others should still have results
        other_checks = [r for r in results if r["check_name"] != "blur"]
        assert len(other_checks) == 4


# ─── Integration test (upload endpoint) ───────────────────────────────────────

class TestUploadEndpoint:
    def _make_test_db(self):
        """Create an in-memory SQLite engine with a static connector so all
        SessionLocal() calls share the same in-process DB (avoids 'no such table'
        errors that occur when each new connection gets a fresh empty :memory: DB)."""
        import sqlite3
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.db import Base

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        return engine, sessionmaker(bind=engine)

    def test_upload_returns_pending_immediately(self, tmp_path, monkeypatch):
        """
        Integration test: POST /images returns 201 with status=pending
        without waiting for analysis to complete.

        Uses SQLite in-process, mocked Redis (no real queue needed).
        """
        # Patch enqueue to avoid needing Redis
        monkeypatch.setattr("app.routes.upload.enqueue_analysis", lambda x: "mock-job-id")

        # Patch settings to point upload_dir at tmp_path (avoids lru_cache issue)
        from app.config import Settings
        mock_settings = Settings(
            database_url="sqlite:///./test_upload.db",
            upload_dir=str(tmp_path),
        )
        monkeypatch.setattr("app.routes.upload.get_settings", lambda: mock_settings)

        # Patch DB dependency to use SQLite
        from app.db import get_db
        from app.main import app
        from fastapi.testclient import TestClient

        engine, TestSession = self._make_test_db()

        def override_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db

        client = TestClient(app)
        image_bytes = make_normal_image_bytes()

        response = client.post(
            "/images",
            files={"file": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
        )

        assert response.status_code == 201
        body = response.json()
        assert "id" in body
        assert body["status"] == "pending"

        # Cleanup
        app.dependency_overrides.clear()
        from app.db import Base
        Base.metadata.drop_all(engine)
        engine.dispose()

    def test_upload_rejects_non_image(self, tmp_path, monkeypatch):
        """Uploading a text file should return 400."""
        monkeypatch.setattr("app.routes.upload.enqueue_analysis", lambda x: "mock-job-id")

        from app.config import Settings
        mock_settings = Settings(upload_dir=str(tmp_path))
        monkeypatch.setattr("app.routes.upload.get_settings", lambda: mock_settings)

        from app.db import get_db, Base
        from app.main import app
        from fastapi.testclient import TestClient

        engine, TestSession = self._make_test_db()

        def override_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)

        response = client.post(
            "/images",
            files={"file": ("doc.txt", io.BytesIO(b"hello world"), "text/plain")},
        )

        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()

    def test_upload_rejects_zero_byte_file(self, tmp_path, monkeypatch):
        """Zero-byte file should return 400."""
        monkeypatch.setattr("app.routes.upload.enqueue_analysis", lambda x: "mock-job-id")

        from app.config import Settings
        mock_settings = Settings(upload_dir=str(tmp_path))
        monkeypatch.setattr("app.routes.upload.get_settings", lambda: mock_settings)

        from app.db import get_db, Base
        from app.main import app
        from fastapi.testclient import TestClient

        engine, TestSession = self._make_test_db()

        def override_db():
            db = TestSession()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app)

        response = client.post(
            "/images",
            files={"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")},
        )

        assert response.status_code == 400

        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()

