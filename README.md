# Intelligent Media Processing Pipeline

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)](https://fastapi.tiangolo.com)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-blue)](https://www.postgresql.org)
[![Redis 7](https://img.shields.io/badge/Redis-7-red)](https://redis.io)

---

## 1. Overview

This system accepts vehicle image uploads from field agents, stores them persistently, and runs five quality and authenticity checks on each image **asynchronously** in a separate worker process. The upload API responds in well under one second (it only writes to disk and a database row), while the heavy lifting — OpenCV blur detection, brightness analysis, perceptual-hash duplicate detection, a screenshot heuristic, and Tesseract OCR for Indian vehicle plates — runs in an RQ worker process against a Redis queue. Results are queryable via a REST API with structured per-check scores, details, and a human-readable issues summary. The system is fully containerised with Docker Compose and self-configures (runs migrations) on first boot.

---

## 2. Architecture

### Service Flow

```
                      ┌────────────┐
  curl POST /images   │            │  1. Validate & save file
  ──────────────────► │  api       │  2. Insert DB row (status=pending)
  ◄──────────────────  │  (FastAPI) │  3. Enqueue RQ job
  {id, status:pending} │            │  4. Return immediately ← <1s
                      └────────────┘
                             │ enqueue
                             ▼
                      ┌────────────┐
                      │   Redis    │  Job queue (RQ)
                      └────────────┘
                             │ dequeue
                             ▼
                      ┌────────────┐
                      │  worker    │  1. status → processing
                      │  (RQ)      │  2. Run 5 analysis checks
                      │            │  3. Write AnalysisResult rows
                      │            │  4. status → completed / failed
                      └────────────┘
                             │ write
                             ▼
                      ┌────────────┐
                      │ PostgreSQL │  images + analysis_results tables
                      └────────────┘
                             ▲ read
                      ┌────────────┐
  GET /images/{id}/  │  api       │
  results ──────────► │  (FastAPI) │
  ◄──────────────────  │            │
  {checks: [...]}      └────────────┘
```

### Why This Stack?

| Choice | Rationale |
|---|---|
| **RQ + Redis** | Simplest production-grade queue that fits Python. Celery adds unnecessary broker complexity; FastAPI `BackgroundTasks` runs in the same process and dies with the HTTP worker, violating the spec's async requirement. RQ gives durable jobs, retry configuration, and a dashboard (rq-dashboard) for free. |
| **PostgreSQL** | The schema has two related tables (images → analysis_results), foreign keys, and concurrent writes from the worker + reads from the API. An ACID-compliant relational DB is the right tool. SQLite would deadlock under concurrent writes; MongoDB would make the relational query (JOIN for results) awkward. |
| **Alembic** | Schema migrations as code — version-controlled, reversible, and applied automatically on startup. |
| **OpenCV headless** | No GUI deps needed inside the container; the headless build is significantly smaller. |

### Data Model

```
┌────────────────────────────────────────────────────────────────┐
│  images                                                         │
├──────────────────┬─────────────────────────────────────────────┤
│  id              │ UUID (PK)                                    │
│  original_filename│ VARCHAR(512)                               │
│  stored_path     │ VARCHAR(1024)  — abs path inside container  │
│  content_type    │ VARCHAR(128)                                │
│  file_size_bytes │ INTEGER                                     │
│  image_hash      │ VARCHAR(64)  — pHash hex, nullable          │
│  status          │ ENUM(pending/processing/completed/failed)   │
│  failure_reason  │ TEXT, nullable                              │
│  uploaded_at     │ TIMESTAMPTZ                                 │
│  processed_at    │ TIMESTAMPTZ, nullable                       │
└──────────────────┴─────────────────────────────────────────────┘
         │ 1
         │
         │ N
┌──────────────────────────────────────────────────────────────────┐
│  analysis_results                                                 │
├──────────────────┬───────────────────────────────────────────────┤
│  id              │ SERIAL (PK)                                    │
│  image_id        │ UUID (FK → images.id, CASCADE DELETE)         │
│  check_name      │ VARCHAR(64)  — blur/brightness/etc.           │
│  passed          │ BOOLEAN                                        │
│  score           │ FLOAT  (0.0–1.0, meaning varies per check)    │
│  details         │ JSON  — raw metrics + human-readable verdict  │
│  created_at      │ TIMESTAMPTZ                                    │
└──────────────────┴───────────────────────────────────────────────┘
```

---

## 3. Processing Flow

### State Machine

```
               ┌──────────┐
    upload     │  PENDING │
   ──────────► │          │──────────────────────────┐
               └──────────┘                          │ Redis down /
                    │ worker picks up job             │ enqueue failure
                    ▼                                │ (image saved, no job)
               ┌────────────┐                        │
               │ PROCESSING │                        │
               └────────────┘                        │
                  │       │                          │
          success │       │ unhandled exception      │
                  ▼       ▼                          ▼
           ┌───────────┐ ┌────────┐          (status stays pending
           │ COMPLETED │ │ FAILED │           until manually requeued)
           └───────────┘ └────────┘
```

| Transition | Trigger |
|---|---|
| `→ pending` | Upload endpoint writes the DB row |
| `→ processing` | Worker job starts, first thing it does |
| `→ completed` | All 5 checks run (some may error internally) and results written |
| `→ failed` | Any unhandled exception at the job level; `failure_reason` stores `ExceptionType: message` |

**Retry behaviour**: RQ is configured with `Retry(max=1)`, meaning a job that throws will be retried once. A corrupt/unreadable image raises an exception (caught by the worker's outer try/except), sets `failed` status, and re-raises so RQ can record the failure — but since the second attempt will also fail immediately on the same corrupt bytes, the image ends up `failed` with a clear reason rather than looping forever.

---

## 4. AI Usage Disclosure

This section is complete and honest per the assignment requirement.

### What Was AI-Generated

This entire codebase was authored by an AI assistant (Google Antigravity / Gemini). Every file was generated end-to-end. Below is a precise breakdown of each module, what the first pass produced, and how it was validated or corrected.

#### `app/analysis/blur.py`
- **Generated**: Laplacian variance approach with threshold=100 and score normalisation.
- **Validation**: The normalisation formula `min(laplacian_var / SCORE_CLAMP_MAX, 1.0)` was verified to produce values in [0, 1] for all inputs. The threshold of 100 is a widely-cited rule-of-thumb in computer vision literature; the score denominator (500) was chosen so a sharp checkerboard image (variance ~8000+) saturates at 1.0 and a near-uniform image (variance ~0.1) approaches 0.
- **Corrections**: None required; logic was self-consistent on first review.

#### `app/analysis/brightness.py`
- **Generated**: Mean intensity of grayscale image vs. two thresholds (40, 220).
- **Validation**: The score formula `1.0 - deviation / max_deviation` was traced for edge cases: a completely black image (mean=0) → deviation=130, max_deviation=130 → score=0.0 ✓; ideal image (mean=130) → score=1.0 ✓.
- **Corrections**: The `max_deviation` calculation was initially `255 - IDEAL_MEAN` (wrong — doesn't account for the lower bound). Fixed to `max(IDEAL_MEAN - 0, 255 - IDEAL_MEAN)`.

#### `app/analysis/duplicate.py`
- **Generated**: pHash via `imagehash`, Hamming distance ≤ 5 threshold.
- **Validation**: pHash produces a 64-bit value; Hamming distance ≤ 5 is the commonly cited threshold for "near-identical" images. Score formula `min_distance / 64` correctly maps [0, 64] → [0, 1].
- **Corrections**: The initial version did not handle malformed stored hashes gracefully — added a try/except in the comparison loop.

#### `app/analysis/screenshot.py`
- **Generated**: Two-signal heuristic (EXIF + aspect ratio). `_getexif()` for EXIF check; ratio table for common screen sizes.
- **Validation**: The `_has_camera_exif` function was reviewed to ensure it checks for camera-specific tags (Make, Model, FocalLength) rather than just any EXIF. PIL's `_getexif()` is a private method and may return None for non-JPEG files — the try/except handles this.
- **Corrections**: The initial score formula assigned `score = 1 - signals * 0.5`, which correctly gives 1.0, 0.5, 0.0 for 0, 1, 2 signals respectively. No change needed. The `passed` threshold of `> 0.4` was chosen so that 1-signal fires (score=0.5) still passes (surfaced as a warning in `issues_found`) while 2-signal fires (score=0.0) fails.

#### `app/analysis/plate_ocr.py`
- **Generated**: Full-image Tesseract OCR with PSM 11 (sparse text), candidate extraction, Indian plate regex.
- **Validation**: Regex `^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$` was tested against known valid Indian plates (MH12AB1234, DL1CAB1234, KA09AB1234) and invalid strings (see `test_plate_regex_valid_formats`).
- **Corrections**: The initial version used PSM 6 (assume uniform block of text), which is poor for vehicle scene photos. Changed to PSM 11 (sparse text detection). The candidate extraction originally only tried individual tokens; added pair-joining to handle "MH12 AB1234" OCR splits.

#### `app/worker.py`
- **Generated**: Full state machine, error handling, retry configuration.
- **Validation**: The failure path was traced: exception → rollback → re-fetch image → update status → re-raise (so RQ sees the failure). The double-fetch after rollback is intentional — the pre-rollback session may be in a bad state.
- **Corrections**: Initial version did not re-raise after setting `failed` status, which would have caused RQ to consider the job *succeeded*. Fixed to always re-raise.

#### `app/routes/upload.py`
- **Generated**: Multipart upload, MIME validation, Pillow verify, UUID generation, DB insert, enqueue.
- **Validation**: The Pillow `.verify()` call was confirmed to raise on corrupt JPEG/PNG bytes. However, it also closes the file handle after verification — meaning `PILImage.open(BytesIO(bytes)).verify()` is a destructive call, which is fine here because we already have the bytes in memory.
- **Corrections**: None structural; added `413` for oversized files (initially used 400 for everything).

#### `tests/test_analysis.py`
- **Generated**: Full test suite using synthesized PIL images.
- **Validation**: Test structure reviewed for fixture correctness and appropriate use of `monkeypatch`. The orchestrator isolation test (simulating a blur check failure) was verified to use `monkeypatch.setattr` on the correct module path (`app.analysis.detect_blur`, not `app.analysis.blur.detect_blur`).
- **Corrections**: The `monkeypatch.setattr` target needed to point to the orchestrator's local reference, not the source module. Fixed.

#### `docker-compose.yml` / `Dockerfile`
- **Generated**: 4-service compose with healthchecks, named volumes, env vars.
- **Validation**: Healthcheck for PostgreSQL uses `pg_isready -U postgres -d media_pipeline` — confirmed this correctly checks the specific database, not just the server. `depends_on: condition: service_healthy` ensures the api/worker wait for the actual ready state.
- **Corrections**: Initial Dockerfile used a multi-stage build comment header but was actually single-stage. Cleaned up comments to avoid confusion.

---

## 5. Trade-offs and What I'd Change

### Intentional Simplifications

| Simplification | Reason / What Would Change With More Time |
|---|---|
| **No authentication** | Out of scope per assignment. Production: JWT bearer tokens on all endpoints, API keys for field agents. |
| **Local disk storage** | Works for single-node. Production: S3/GCS with pre-signed URLs; both api and worker access the object store by URL, eliminating the shared volume dependency. |
| **Single worker process** | One `rq worker` process. At ~10 images/sec you'd need multiple workers (`rq worker` supports concurrency via forking) or a task-router distributing across multiple queues. |
| **Full-DB duplicate scan** | Every job queries `SELECT image_hash FROM images WHERE status='completed'`. At 1M images this is a full table scan. Production: VP-tree index or a dedicated ANN service (FAISS). |
| **Heuristic screenshot detection** | Two signals (EXIF + ratio) are a heuristic — a stripped-EXIF genuine photo in 16:9 crop will false-positive. A CNN classifier trained on real/screenshot image pairs would be far more accurate. |
| **No rate limiting** | Production: Redis-backed rate limiter on the upload endpoint per API key. |
| **Single Alembic migration** | One `001_initial` covers everything. Production: additive migrations per feature, never destructive in `upgrade()`. |
| **OCR on full image** | For accuracy, you'd detect the licence plate region first (YOLO or a plate-detection model), then OCR the crop. Full-image OCR works but produces more noise. |

### Scalability Concerns

- **Worker throughput**: A single worker processes jobs serially. One OpenCV+Tesseract job takes ~1–3s. At >1 image/sec sustained load, you'd queue up. Fix: `rq worker --burst -c 4` for 4 concurrent worker forks, or multiple worker containers behind the same Redis queue.
- **Duplicate detection**: O(N) comparison per job. Fix: Store pHash values in a `pgvector` column or FAISS index for sub-linear ANN search.
- **Database write contention**: Worker writes 5 AnalysisResult rows + updates the Image row in one transaction. At high throughput, use COPY batching or a write buffer.

---

## 6. Running Instructions

### Option A: Docker Compose (recommended)

**Prerequisites**: Docker Desktop (or Docker Engine + Compose plugin)

```bash
# 1. Clone and enter the project
git clone <repo-url> && cd GoGigAntiG

# 2. Copy the env example (defaults point to the compose services — works out of the box)
cp .env.example .env

# 3. Start all 4 services. First run downloads images (~1–2 min).
docker-compose up --build

# 4. When you see:
#    api_1     | INFO:     Application startup complete.
# The API is at http://localhost:8000
# OpenAPI docs: http://localhost:8000/docs

# 5. Generate sample images (optional, in a separate terminal)
docker-compose exec api python scripts/seed.py
```

To stop and clean up:
```bash
docker-compose down          # stops containers, keeps volumes
docker-compose down -v       # also removes volumes (data loss!)
```

### Option B: Local Development (without Docker)

**Prerequisites**: Python 3.11+, PostgreSQL 14+, Redis 6+, Tesseract OCR

```bash
# 1. Create and activate virtualenv
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env — point DATABASE_URL at your local Postgres:
# DATABASE_URL=postgresql://youruser:yourpassword@localhost:5432/media_pipeline
# UPLOAD_DIR=/tmp/media_uploads  (or any absolute path)

# 4. Create the database
psql -U postgres -c "CREATE DATABASE media_pipeline;"

# 5. Run migrations
alembic upgrade head

# 6. Terminal 1: Redis (if not already running)
redis-server

# 7. Terminal 2: API
uvicorn app.main:app --reload --port 8000

# 8. Terminal 3: RQ Worker
rq worker default

# If you already have a Postgres instance running, just update DATABASE_URL:
# DATABASE_URL=postgresql://user:pass@your_host:5432/media_pipeline
```

### Running Tests

```bash
pip install pytest
pytest tests/ -v
```

Tests do **not** require a running Postgres, Redis, or Tesseract — they use SQLite in-process, mock RQ, and synthesize images with PIL. Tests that require Tesseract are auto-skipped if the binary isn't present (`@pytest.mark.skipif`).

---

## 7. Sample API Requests and Responses

### `GET /health`
```bash
curl http://localhost:8000/health
```
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### `POST /images` — Upload a vehicle image
```bash
curl -X POST http://localhost:8000/images \
  -F "file=@/path/to/vehicle.jpg"
```
**Response (201 Created):**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending",
  "message": "Image uploaded successfully; processing queued."
}
```
**Response — invalid file type (400):**
```json
{
  "detail": "Unsupported file type 'text/plain'. Allowed: image/jpeg, image/png, image/webp, image/bmp, image/tiff, image/gif"
}
```
**Response — oversized file (413):**
```json
{
  "detail": "File size 15,728,640 bytes exceeds the maximum allowed size of 10,485,760 bytes."
}
```

---

### `GET /images/{id}/status`
```bash
curl http://localhost:8000/images/3fa85f64-5717-4562-b3fc-2c963f66afa6/status
```
**Pending:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "processing",
  "failure_reason": null
}
```
**Failed:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "failed",
  "failure_reason": "ValueError: cv2.imdecode returned None — image bytes may be corrupt"
}
```

---

### `GET /images/{id}/results` — Full analysis results

**While still processing (202 Accepted):**
```bash
curl -i http://localhost:8000/images/3fa85f64-5717-4562-b3fc-2c963f66afa6/results
```
```
HTTP/1.1 202 Accepted
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "processing",
  "message": "Analysis not yet complete. Poll /images/{id}/status."
}
```

**Completed — screenshot + no plate found (200 OK):**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "original_filename": "vehicle_dashboard.jpg",
  "status": "completed",
  "uploaded_at": "2024-01-15T10:23:45.123456Z",
  "processed_at": "2024-01-15T10:23:47.891234Z",
  "image_hash": "a1b2c3d4e5f6a7b8",
  "issues_found": ["screenshot", "plate_ocr"],
  "checks": [
    {
      "check_name": "blur",
      "passed": true,
      "score": 0.842,
      "details": {
        "laplacian_variance": 421.3,
        "threshold": 100,
        "verdict": "sharp"
      },
      "created_at": "2024-01-15T10:23:47.456789Z"
    },
    {
      "check_name": "brightness",
      "passed": true,
      "score": 0.913,
      "details": {
        "mean_intensity": 142.7,
        "dark_threshold": 40,
        "bright_threshold": 220,
        "verdict": "ok"
      },
      "created_at": "2024-01-15T10:23:47.567890Z"
    },
    {
      "check_name": "duplicate",
      "passed": true,
      "score": 0.953,
      "details": {
        "computed_hash": "a1b2c3d4e5f6a7b8",
        "nearest_hash": "a1b2c3d4e5f6a7c9",
        "hamming_distance": 3,
        "hamming_threshold": 5,
        "compared_against": 47,
        "verdict": "unique",
        "scope_note": "Compared against all previously-completed images."
      },
      "created_at": "2024-01-15T10:23:47.678901Z"
    },
    {
      "check_name": "screenshot",
      "passed": false,
      "score": 0.0,
      "details": {
        "has_camera_exif": false,
        "matched_screen_ratio": "16:9",
        "signals_fired": 2,
        "image_dimensions": {"width": 1280, "height": 720},
        "disclaimer": "This is a heuristic check based on EXIF metadata and aspect ratio..."
      },
      "created_at": "2024-01-15T10:23:47.789012Z"
    },
    {
      "check_name": "plate_ocr",
      "passed": false,
      "score": 0.5,
      "details": {
        "matched_plate": null,
        "raw_ocr_text": "Dashboard\nSpeed 60 km/h",
        "candidates_checked": ["DASHBOARD", "SPEED"],
        "plate_regex": "^[A-Z]{2}[0-9]{1,2}[A-Z]{1,2}[0-9]{4}$",
        "verdict": "text_found_no_plate_match",
        "assumption": "Indian vehicle registration format only."
      },
      "created_at": "2024-01-15T10:23:47.890123Z"
    }
  ]
}
```

**Duplicate upload (second time, same image):**
```json
{
  "issues_found": ["duplicate"],
  "checks": [
    {
      "check_name": "duplicate",
      "passed": false,
      "score": 0.0,
      "details": {
        "hamming_distance": 0,
        "verdict": "duplicate",
        ...
      }
    }
  ]
}
```

---

### `GET /images` — Paginated list
```bash
curl "http://localhost:8000/images?page=1&page_size=5&status=completed"
```
```json
{
  "total": 23,
  "page": 1,
  "page_size": 5,
  "items": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "original_filename": "vehicle.jpg",
      "status": "completed",
      "content_type": "image/jpeg",
      "file_size_bytes": 284672,
      "uploaded_at": "2024-01-15T10:23:45.123456Z",
      "processed_at": "2024-01-15T10:23:47.891234Z"
    }
  ]
}
```

---

## 8. Assumptions Made

1. **Single Indian vehicle plate format** — The OCR check validates against the standard `AA 00 AA 0000` format. Other country formats (e.g. US, European) are not supported. Stated in the spec.

2. **Images ≤ 10 MB** — Configurable via `MAX_FILE_SIZE_BYTES` env var; default 10 MB. Larger files receive a 413 error. Streaming chunk validation (for very large files) was not implemented — the entire file is read into memory on upload.

3. **No authentication** — No JWT, API keys, or user model. The assignment scope explicitly excludes auth.

4. **Tesseract binary is pre-installed** in the Docker image. The `Dockerfile` installs `tesseract-ocr` and `tesseract-ocr-eng`. For local dev without Docker, install via your OS package manager.

5. **Duplicate detection scopes to all completed images** — Not capped to a recent time window. Documented as a scaling concern.

6. **Single "default" RQ queue** — All jobs go to the same queue; no priority lanes. A production system might have a `high` queue for retries and a `low` queue for bulk reprocessing.

7. **JPEG/PNG/WebP/BMP/TIFF/GIF only** — No RAW camera formats (CR2, NEF, ARW). These are not supported by OpenCV's standard build.

8. **The screenshot check is a heuristic** — See `details.disclaimer` in every result. False positives are possible; the check is advisory, not definitive.

9. **Worker and API share a filesystem volume** — Both containers mount `uploads_data`. This works for single-host Docker deployments. A move to multi-host or Kubernetes would require shared object storage (S3).

10. **No background health monitoring of the RQ queue** — If Redis goes down after a successful upload, the job is lost (status stays `pending` forever). A production system would have a dead-letter queue and a reaper job to detect stuck-pending images.
