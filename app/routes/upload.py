"""
app/routes/upload.py — POST /images endpoint.

Responsibilities
----------------
1. Validate the uploaded file: MIME type, non-zero size, max size limit.
2. Save the file to UPLOAD_DIR under a UUID-based name.
3. Insert an Image row with status=pending.
4. Enqueue the analysis job (non-blocking).
5. Return {id, status} immediately — must not wait for processing.

File validation is intentionally strict at the boundary so the worker
never receives garbage. A second defensive validation also runs inside
the worker (belt-and-suspenders).
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Image, ImageStatus
from app.queue import enqueue_analysis
from app.schemas import UploadResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/images",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a vehicle image",
    description=(
        "Accept a multipart image upload. Validates MIME type and file size. "
        "Saves the file, inserts a DB row with status=`pending`, and enqueues "
        "an analysis job. Returns immediately with the image ID."
    ),
)
async def upload_image(
    file: UploadFile = File(..., description="Vehicle image (JPEG, PNG, WebP, BMP, TIFF, GIF)"),
    db: Session = Depends(get_db),
) -> UploadResponse:
    settings = get_settings()

    # ── 1. MIME type validation ─────────────────────────────────────────────
    if file.content_type not in settings.allowed_content_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                f"Allowed: {', '.join(settings.allowed_content_types)}"
            ),
        )

    # ── 2. Read file bytes (with size guard) ────────────────────────────────
    # We read in one shot to check size; for production use streaming chunks.
    file_bytes = await file.read()
    file_size = len(file_bytes)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    if file_size > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File size {file_size:,} bytes exceeds the maximum "
                f"allowed size of {settings.max_file_size_bytes:,} bytes."
            ),
        )

    # ── 3. Quick image sanity check using Pillow ────────────────────────────
    try:
        from io import BytesIO
        from PIL import Image as PILImage, UnidentifiedImageError
        PILImage.open(BytesIO(file_bytes)).verify()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content does not appear to be a valid image (failed Pillow verification).",
        )

    # ── 4. Generate UUID and save file ──────────────────────────────────────
    image_id = uuid.uuid4()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Derive extension from content type for clarity
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/bmp": ".bmp",
        "image/tiff": ".tiff",
        "image/gif": ".gif",
    }
    ext = ext_map.get(file.content_type, ".bin")
    stored_filename = f"{image_id}{ext}"
    stored_path = upload_dir / stored_filename

    stored_path.write_bytes(file_bytes)
    logger.info(
        "Upload received: id=%s filename=%s size=%d content_type=%s stored_path=%s",
        image_id, file.filename, file_size, file.content_type, stored_path,
    )

    # ── 5. Insert DB row ────────────────────────────────────────────────────
    image = Image(
        id=image_id,
        original_filename=file.filename or stored_filename,
        stored_path=str(stored_path),
        content_type=file.content_type,
        file_size_bytes=file_size,
        status=ImageStatus.pending,
    )
    db.add(image)
    db.commit()
    db.refresh(image)

    # ── 6. Enqueue analysis job ─────────────────────────────────────────────
    job_id = enqueue_analysis(str(image_id))
    if job_id:
        logger.info("Job enqueued: job_id=%s image_id=%s", job_id, image_id)
    else:
        logger.warning(
            "Failed to enqueue job for image %s (Redis may be unavailable). "
            "Image row is persisted; re-queuing may be required.",
            image_id,
        )

    return UploadResponse(
        id=image_id,
        status=image.status.value,
        message=(
            "Image uploaded successfully; processing queued."
            if job_id
            else "Image saved but job queueing failed — Redis may be unavailable."
        ),
    )
