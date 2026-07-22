"""
app/routes/results.py — GET endpoints for image status and results.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Image, ImageStatus
from app.schemas import (
    CheckResult,
    ImageListItem,
    ImageListResponse,
    ImageResultsResponse,
    ImageStatusResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Health ──────────────────────────────────────────────────────────────────

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness check",
    tags=["Health"],
)
def health_check() -> HealthResponse:
    """Trivial liveness probe. Returns 200 OK when the API process is running."""
    return HealthResponse()


# ─── Status ──────────────────────────────────────────────────────────────────

@router.get(
    "/images/{image_id}/status",
    response_model=ImageStatusResponse,
    summary="Get processing status for an image",
    tags=["Images"],
)
def get_image_status(image_id: str, db: Session = Depends(get_db)) -> ImageStatusResponse:
    """Return the current status (pending/processing/completed/failed) for an image."""
    image = db.query(Image).filter(Image.id == image_id).first()
    if image is None:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")
    return ImageStatusResponse.model_validate(image)


# ─── Full results ─────────────────────────────────────────────────────────────

@router.get(
    "/images/{image_id}/results",
    summary="Get full analysis results for an image",
    tags=["Images"],
)
def get_image_results(image_id: str, db: Session = Depends(get_db)):
    """
    Return all 5 check results with scores and details.

    - If status is `completed`: returns 200 with full results.
    - If status is `pending` or `processing`: returns 202 with current status.
    - If status is `failed`: returns 200 with failure reason and empty checks.
    - If not found: returns 404.
    """
    image = (
        db.query(Image)
        .options(selectinload(Image.results))
        .filter(Image.id == image_id)
        .first()
    )
    if image is None:
        raise HTTPException(status_code=404, detail=f"Image '{image_id}' not found.")

    if image.status in (ImageStatus.pending, ImageStatus.processing):
        # 202 Accepted: processing is in progress
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={
                "id": str(image.id),
                "status": image.status.value,
                "message": "Analysis not yet complete. Poll /images/{id}/status.",
            },
        )

    # Build issues list
    issues_found = [
        r.check_name for r in image.results if not r.passed
    ]

    checks = [CheckResult.model_validate(r) for r in image.results]

    return ImageResultsResponse(
        id=image.id,
        original_filename=image.original_filename,
        status=image.status.value,
        uploaded_at=image.uploaded_at,
        processed_at=image.processed_at,
        image_hash=image.image_hash,
        issues_found=issues_found,
        checks=checks,
    )


# ─── List ─────────────────────────────────────────────────────────────────────

@router.get(
    "/images",
    response_model=ImageListResponse,
    summary="List uploaded images (paginated)",
    tags=["Images"],
)
def list_images(
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(default=None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db),
) -> ImageListResponse:
    """Paginated list of all uploaded images with their processing status."""
    query = db.query(Image)

    if status_filter:
        try:
            status_enum = ImageStatus(status_filter)
            query = query.filter(Image.status == status_enum)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status_filter}'. Valid values: {[s.value for s in ImageStatus]}",
            )

    total = query.count()
    images = (
        query.order_by(Image.uploaded_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ImageListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[ImageListItem.model_validate(img) for img in images],
    )
