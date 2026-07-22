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

AI tools were used as a development assistant throughout this project, similar to how developers use documentation, search engines, or code assistants. The overall project design, integration of components, testing, debugging, deployment, and final verification were completed by me.

### Where AI was used

- To understand unfamiliar concepts and compare technologies before implementation.
- To generate boilerplate code and accelerate development of some backend and frontend components.
- To get suggestions while improving the user interface and refining the dashboard.
- To troubleshoot deployment issues on Docker and Railway when I encountered configuration problems.
- To clarify errors, understand logs, and explore possible fixes during development.

### Where AI output was wrong or needed correction

- An early Docker networking failure (`worker` unable to resolve the `redis` hostname) was not something AI-generated configuration flagged in advance — it turned out to be caused by a stale Docker network left over from an earlier failed run, which I diagnosed myself by comparing container creation logs across successive runs and fixed with a full `docker compose down -v --remove-orphans` teardown.
- The RQ worker's start command had a duplicate `--serializer`/`-S` flag (set in more than one place across the Dockerfile and compose configuration), which surfaced as a recurring warning in every worker log line until I traced and removed the duplicate.
- A test fixture used an invalid Indian plate number (`DL1CAB1234`, which exceeds the two-character series limit for that format) — I checked the plate regex independently against the actual format spec to confirm the fixture was the bug, not the validation logic, before correcting it.

### My contribution

I was responsible for:

- Designing the overall workflow and deciding how different components should interact.
- Integrating the backend, database, Redis, worker, and frontend into a complete application.
- Testing every feature and verifying that the generated code worked correctly.
- Debugging issues related to Docker, Redis, Railway deployment, database connections, and application logic.
- Making implementation decisions, modifying generated code where necessary, and ensuring the final application met the project requirements.

AI helped speed up development, but the final project required manual integration, testing, debugging, deployment, and verification before completion.

---

## 5. Trade-offs

### 5.1 Intentional Simplifications

To keep the project focused within the assignment scope and timeline, I made the following simplifications:

| Simplification | Reason |
|---|---|
| No authentication or authorization | The assignment focused on image processing rather than user management. |
| Local file storage | Images are stored on a shared local volume instead of cloud storage to simplify deployment. |
| Single background worker | One RQ worker is sufficient for demonstrating asynchronous processing. |
| Heuristic screenshot detection | Screenshot detection is based on EXIF metadata and aspect ratio rather than a trained machine learning model. |
| Full-image OCR | OCR is performed on the entire image instead of first detecting the license plate region. |
| Simple duplicate detection | Images are compared using perceptual hashes stored in the database rather than an optimized similarity index. |

### 5.2 What I Would Improve With More Time

If more development time were available, I would enhance the system by:

- Adding JWT authentication and role-based access control.
- Replacing local storage with cloud object storage such as Amazon S3 or Google Cloud Storage.
- Detecting the license plate region before running OCR to improve accuracy.
- Using a machine learning model for screenshot detection instead of heuristic rules.
- Adding rate limiting and request throttling.
- Improving the frontend with real-time progress updates using WebSockets.

### 5.3 Scalability Considerations

The current implementation is suitable for small to moderate workloads but would require improvements for large-scale deployment.

Current limitations include:

- A single RQ worker processes jobs sequentially, which limits throughput.
- Duplicate detection compares against all previously processed images, making it slower as the dataset grows.
- Local file storage is suitable only for a single server deployment.

To improve scalability, I would:

- Deploy multiple worker instances processing the same Redis queue.
- Use cloud object storage for uploaded images.
- Replace linear duplicate comparison with an indexed similarity search solution such as FAISS or pgvector.
- Add database indexing and caching for frequently accessed queries.

### 5.4 Failure Handling

The system includes basic failure handling to improve reliability.

Current mechanisms include:

- Input validation for file type and file size.
- Retry of failed background jobs using RQ.
- Database status tracking (pending, processing, completed, failed).
- Error messages stored with failed jobs for easier debugging.

Areas for future improvement include:

- Dead-letter queues for permanently failed jobs.
- Automatic retry with exponential backoff.
- Monitoring and alerting for worker failures.
- Automatic cleanup of orphaned uploaded files.
- Detection and recovery of jobs that remain in the pending state for too long.

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
