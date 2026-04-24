# ARCHITECTURE.md

# System Architecture

## 1. Overview

This application is a production-style web stack for daily tracking of biomedicine, biotech, pharma, and cell therapy news.

The system is composed of:

- a Next.js frontend for the user interface
- a FastAPI backend for typed API delivery
- a Python worker for scheduled ingestion, classification, and summary generation
- a PostgreSQL database for persistent storage
- an Nginx reverse proxy as the single public entrypoint
- Docker Compose for orchestration

Only Nginx is exposed publicly. All other services communicate over the internal Docker network.

---

## 2. Architecture goals

The architecture is designed to satisfy these goals:

1. Keep deployment simple and production-like.
2. Separate UI rendering, API serving, background ingestion, and storage.
3. Make daily ingestion safe to rerun.
4. Preserve source traceability for every news item.
5. Ensure the homepage remains available even if a scheduled job fails.
6. Support future growth without forcing a major rewrite.

---

## 3. High-level system diagram

Plain-text view of the system:

    [User Browser]
          |
          v
       [Nginx]
       /     \
      v       v
[Next.js]   [FastAPI]
                |
                v
          [PostgreSQL]
                ^
                |
             [Worker]
            /   |    \
           v    v     v
      [Sources][Rules][GLM5]

Where:
- Sources = public news pages / feeds
- Rules = normalization, deduplication, and deterministic category logic
- GLM5 = server-side model endpoint already available in the target environment

---

## 4. Service responsibilities

## 4.1 Nginx

### Role
Nginx is the only public-facing service.

### Responsibilities
- listen on one public port
- route `/` to the frontend service
- route `/api/` to the backend service
- provide a stable single entrypoint for the application
- support future HTTPS termination if needed

### Constraints
- do not expose frontend, backend, worker, or database directly to the public network
- keep routing simple and readable

---

## 4.2 Frontend

### Stack
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui

### Responsibilities
- render the homepage
- display the daily summary
- render category filters
- display the masonry-style news feed
- show loading, empty, and error states
- consume backend APIs through `/api`

### Design principles
- information-dense but readable
- calm, credible visual style
- responsive across desktop, tablet, and mobile
- server components by default
- client components only where interaction requires them

### Recommended directory focus
- `frontend/app/`
- `frontend/components/`
- `frontend/lib/`

---

## 4.3 Backend API

### Stack
- FastAPI
- Pydantic
- SQLAlchemy or SQLModel
- PostgreSQL driver of choice

### Responsibilities
- serve normalized news items
- serve the stored daily summary
- expose category metadata
- expose a manual refresh endpoint
- expose tracked-product CRUD-lite and timeline backfill endpoints
- centralize typed request/response schemas

### API philosophy
- thin route handlers
- business logic in services
- explicit response contracts
- no unvalidated model output returned as trusted structured data

### Recommended directory focus
- `backend/app/api/`
- `backend/app/core/`
- `backend/app/models/`
- `backend/app/schemas/`
- `backend/app/services/`

---

## 4.4 Worker

### Stack
- Python
- shared backend models and services where practical
- APScheduler or equivalent internal scheduler

### Responsibilities
- fetch configured sources
- parse and normalize candidate items
- deduplicate
- classify
- enrich items with GLM5
- generate the daily rollup summary
- persist results to PostgreSQL
- produce structured logs

### Scheduling pattern
Recommended MVP scheduling:
- one morning main run
- one midday supplementary run
- one evening supplementary run

### Important constraint
Worker failure must not bring down:
- the frontend
- the backend API
- the database

---

## 4.5 PostgreSQL

### Responsibilities
- store normalized news items
- store generated daily summaries
- store tracked products, product-news links, and product timeline events
- support category filtering and time-based ordering
- preserve enough history for future trend and archive features

### Design principles
- use stable normalized fields
- store timestamps in UTC internally
- preserve source URL and source name
- keep schema ready for future indexing and aggregation

---

## 5. Request flow

A normal user-facing request follows this path:

1. the browser requests the homepage
2. Nginx receives the request
3. Nginx routes `/` traffic to the frontend
4. the frontend requests `/api/news` and `/api/news/today-summary`
5. Nginx proxies `/api/*` traffic to the backend
6. the backend queries PostgreSQL
7. the backend returns typed JSON payloads
8. the frontend renders the daily summary and feed

This keeps the browser unaware of internal service boundaries.

---

## 6. Ingestion flow

A scheduled ingestion run follows this path:

1. the worker starts a scheduled run
2. the worker fetches configured public sources
3. the worker extracts candidate news items
4. the worker normalizes fields such as title, URL, source, time, and content text
5. the worker deduplicates items
6. the worker applies rule-based classification
7. the worker calls GLM5 for enrichment and ambiguous classification refinement where needed
8. the worker writes normalized news items to PostgreSQL
9. the worker selects important same-day items, with a controlled latest-item fallback if same-day volume is too sparse for the MVP summary block
10. the worker generates and stores the daily summary

---

## 7. Product tracking flow

The repository also supports manually curated product tracking for a specific asset such as a drug, cell therapy program, or platform candidate.

Flow:

1. a user creates a tracked product from the frontend
2. the backend stores the product profile with aliases, company, and indications
3. the backend searches existing `news_items` for obvious matches
4. the backend fetches targeted Google News RSS result pages for the product and company
5. fetched candidates are normalized, enriched, and upserted into the shared news store
6. GLM5 is used to decide whether ambiguous news items are truly about the tracked product
7. GLM5 is used again to extract structured milestone events from linked news
8. extracted events are deduplicated by a stable event hash and stored in product timeline tables
9. the frontend renders the product timeline and linked evidence news

This design keeps product tracking aligned with the existing ingestion pipeline instead of creating a separate free-form timeline store.
11. the frontend later reads those stored results through the backend API

---

## 7. Core data entities

## 7.1 News item

Each news item should include at least:

- `id`
- `title`
- `canonical_url`
- `source_name`
- `published_at`
- `category`
- `short_summary`
- `content_text`
- `image_url`
- `language`
- `title_hash`
- `created_at`
- `updated_at`

Recommended enrichment fields:

- `entities`
- `importance_score`
- `relevance_to_cell_therapy`

### Notes
- `canonical_url` is used for source traceability and deduplication
- `title_hash` supports repeated-run idempotency
- `short_summary` is the UI-facing summary, not the raw article text

---

## 7.2 Daily summary

Each daily summary should include at least:

- `id`
- `summary_date`
- `daily_summary`
- `top_events`
- `trend_signal`
- `category_counts`
- `model_name`
- `generated_at`

### Notes
- there should usually be only one summary per date
- `top_events` should be structured enough for frontend rendering
- `category_counts` supports future analytics and lightweight charts

---

## 8. Classification architecture

## 8.1 Fixed taxonomy

The application uses this fixed category list:

- Financing
- Clinical/Regulatory Progress
- R&D
- Partnership/Licensing
- M&A/Organization
- Manufacturing/CMC
- Policy/Industry Environment
- Other

### Constraint
These labels must stay aligned across:
- backend enums or constants
- database values
- frontend filters
- daily summary logic
- documentation

---

## 8.2 Classification strategy

Use a hybrid strategy:

1. deterministic keyword and rule pass first
2. LLM refinement only for ambiguous cases
3. final validation against the allowed category list before persistence

### Why this strategy
This balances:
- predictability
- lower cost
- easier debugging
- stable UI behavior
- reasonable flexibility for ambiguous stories

---

## 9. GLM5 integration architecture

## 9.1 Purpose of GLM5

GLM5 is used for two related but distinct tasks:

### Per-item enrichment
For individual news items, GLM5 can produce fields such as:
- `one_line_summary`
- `category`
- `entities`
- `importance_score`
- `relevance_to_cell_therapy`

### Daily rollup generation
For the homepage summary block, GLM5 can produce fields such as:
- `daily_summary`
- `top_events`
- `trend_signal`
- `category_counts`

---

## 9.2 Output contract

At the service boundary, GLM5 output must be structured JSON.

Validation should check:
- required keys exist
- values have expected types
- category labels are legal
- arrays stay within expected size bounds
- text fields are non-empty and not placeholder garbage

### Important rule
Do not persist unvalidated free-form model output as trusted structured data.

---

## 9.3 Failure handling

If model output validation fails:

1. retry once with stricter format instructions
2. if validation still fails, log the failure clearly
3. fall back to a deterministic or null-safe path

This prevents one malformed response from breaking the application state.

---

## 10. Deduplication architecture

Industry news is frequently syndicated or reposted. A single event may appear across multiple sources.

Use layered deduplication:

1. canonical URL equality
2. normalized title hash
3. optional near-duplicate similarity check for likely reposts

### Objective
Prevent repeated ingestion runs and syndicated reposts from flooding the feed with obvious duplicates.

### Idempotency requirement
Repeated worker runs should not create duplicate rows for the same event unless the product explicitly changes to preserve source-level duplicates.

---

## 11. Deployment architecture

## 11.1 Compose services

Planned Docker Compose services:

- `nginx`
- `frontend`
- `backend`
- `worker`
- `postgres`

---

## 11.2 Public exposure model

Only one public port is exposed:
- from the `nginx` service

All other services remain internal to the Docker network.

This reduces exposure and simplifies routing.

---

## 11.3 Internal routing model

Nginx should proxy:
- `/` to `frontend:3000`
- `/api/` to `backend:8000`

The browser should never need to know internal service names.

---

## 11.4 Persistence

Use a named Docker volume for PostgreSQL data persistence.

Recommended initial volume:
- `postgres_data`

This ensures data survives container restarts and image rebuilds.

Phase 4 implementation:
- the FastAPI backend uses SQLAlchemy with `DATABASE_URL`
- startup initializes the minimal `news_items` and `daily_summaries` tables
- deterministic sample data is opt-in via `SEED_SAMPLE_DATA=true`
- API reads for news and daily summaries are PostgreSQL-backed
- the worker ingests a small RSS source set from `config/sources.json` or `INGESTION_SOURCES_JSON`, normalizes feed entries, deduplicates by canonical URL, normalized title hash, and conservative near-duplicate title matching
- deterministic classification runs first; GLM5 item refinement is reserved for ambiguous cases when configured
- GLM5 calls are isolated behind a dedicated client, use bounded retry/backoff for transient failures, and fall back deterministically when unconfigured or malformed
- daily summary top events are validated as structured objects before JSON persistence
- backend manual refresh has a process-local overlap guard; the scheduled worker still relies on scheduler `max_instances=1`

---

## 12. Environment variable model

The system should rely on environment variables rather than hardcoded secrets or addresses.

Recommended variables include:

### Frontend
- `NEXT_PUBLIC_APP_NAME`
- `NEXT_PUBLIC_API_BASE_PATH`

### Backend and Worker
- `DATABASE_URL`
- `GLM5_BASE_URL`
- `GLM5_API_KEY`
- `GLM5_MODEL_NAME`
- `INGESTION_TIMEZONE`
- `INGESTION_SCHEDULE_HOURS`
- `INGESTION_MAX_ITEMS_PER_SOURCE`
- `INGESTION_SOURCES_JSON`
- `WORKER_RUN_ON_STARTUP`
- `SOURCE_CONFIG_PATH`
- `SOURCE_REQUEST_TIMEOUT_SECONDS`
- `SOURCE_REQUEST_MAX_ATTEMPTS`
- `SOURCE_REQUEST_BACKOFF_SECONDS`
- `GLM5_REQUEST_TIMEOUT_SECONDS`
- `GLM5_REQUEST_MAX_ATTEMPTS`
- `GLM5_REQUEST_BACKOFF_SECONDS`
- `SEED_SAMPLE_DATA`
- `LOG_LEVEL`
- `LOG_FORMAT`
- `ADMIN_REFRESH_TOKEN`
- `APP_ENV`

### Postgres
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

### Deployment
- `APP_PORT`

### Rule
Any newly required environment variable must also be documented in:
- `.env.example`
- `docs/DEPLOYMENT.md`

For the default MVP deployment path, only one host-visible port should be published from Docker Compose, and it should belong to Nginx.

---

## 13. Database schema sketch

## 13.1 `news_items`

Suggested columns:

- `id`
- `title`
- `canonical_url`
- `source_name`
- `published_at`
- `category`
- `short_summary`
- `content_text`
- `image_url`
- `language`
- `title_hash`
- `entities_json`
- `importance_score`
- `relevance_to_cell_therapy`
- `created_at`
- `updated_at`

Suggested indexes:

- unique or near-unique handling on `canonical_url`
- index on `published_at`
- index on `category`
- index on `title_hash`

---

## 13.2 `daily_summaries`

Suggested columns:

- `id`
- `summary_date`
- `daily_summary`
- `top_events_json`
- `trend_signal`
- `category_counts_json`
- `model_name`
- `generated_at`
- `created_at`
- `updated_at`

Suggested indexes:

- unique index on `summary_date`

---

## 14. Operational concerns

## 14.1 Logging

At minimum, log:
- ingestion run start and end
- source fetch success and failure
- parse failures
- dedupe counts
- classification failures
- GLM5 validation failures
- database write outcomes

Logs should make it possible to diagnose:
- which source failed
- how many items were fetched
- how many items were skipped
- whether a daily summary was generated
- which transient failures were retried and with what status code

For container-first operations, default text logs are acceptable, but `LOG_FORMAT=json` should preserve structured fields such as retry metadata and source identifiers for machine parsing.

---

## 14.2 Health checks

Recommended health surfaces:
- backend health endpoint such as `GET /api/health`
- database readiness check
- container restart policies in Docker Compose
- nginx edge health such as `GET /nginx-health`

Health checks help Nginx and Compose handle startup sequencing more safely.

Operational split:

- `GET /nginx-health` answers whether the public reverse proxy process is alive
- `GET /api/health` answers whether the backend is alive and can still reach PostgreSQL

External uptime monitoring should target `/api/health` through Nginx. Container-local compose health checks may use either route depending on whether the concern is proxy liveness or backend/database liveness.

---

## 14.3 Documentation alignment

When architecture, environment variables, routing, or deployment steps change, update the relevant files in the same task.

At minimum keep these aligned:
- `docs/PRD.md`
- `docs/ARCHITECTURE.md`
- `docs/API_SPEC.md`
- `docs/DEPLOYMENT.md`
- `docker-compose.yml`
- `infra/nginx/default.conf`

---

## 15. Future extension points

This architecture should support later additions such as:

- keyword search
- entity extraction and company pages
- weekly and monthly summaries
- source administration
- archived historical views
- alerting or digest export
- modality or disease-area tagging
- richer analytics and trend views

The MVP should not implement all of these now, but the architecture should not block them.

---

## 16. Summary

This system uses a clean separation of concerns:

- Nginx handles public routing
- Next.js handles presentation
- FastAPI handles typed data delivery
- the worker handles background ingestion and summarization
- PostgreSQL stores normalized application state
- GLM5 provides structured enrichment and daily summary generation

The key operating principle is simple:
build a reliable daily intelligence dashboard first, then expand features incrementally without breaking the core ingestion-to-display pipeline.
