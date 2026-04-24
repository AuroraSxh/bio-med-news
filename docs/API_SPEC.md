# API_SPEC.md

# API Specification

## 1. Overview

This document defines the MVP API surface for the Biomed / Cell Therapy Daily Intelligence Dashboard.

The API is served by the FastAPI backend and exposed publicly through Nginx under the `/api` path.

Example public pattern:

- `http://118.178.195.6:<APP_PORT>/api/...`

The API is intended primarily for the repository's own frontend, but it should remain clear, typed, and maintainable.

---

## 2. Design principles

The API should follow these principles:

- typed request and response contracts
- stable field naming
- explicit success and error states
- source traceability for news items
- predictable filtering and ordering
- no raw unvalidated LLM output exposed as trusted structured fields

---

## 3. Base path

All routes are served under:

- `/api`

Examples:
- `/api/health`
- `/api/news`
- `/api/news/today-summary`
- `/api/categories`
- `/api/products`
- `/api/admin/refresh`

---

## 4. Content type

Unless otherwise noted, the API uses:

- request content type: `application/json`
- response content type: `application/json`

---

## 5. Time handling

Time-related rules:

- backend stores timestamps in UTC internally
- API responses should use ISO 8601 timestamps
- frontend is responsible for final display formatting if localized presentation is desired

Recommended timestamp format example:

- `2026-04-12T08:30:00Z`

---

## 6. Authentication model

### MVP assumption

Public read endpoints are unauthenticated.

These endpoints are read-only and intended for homepage rendering:
- `GET /api/health`
- `GET /api/news`
- `GET /api/news/today-summary`
- `GET /api/categories`
- `GET /api/products`
- `GET /api/products/{slug}`
- `GET /api/products/{slug}/timeline`
- `GET /api/products/{slug}/sources`

### Admin endpoint

The refresh endpoint should require an admin token.

Recommended approach:
- header-based token validation
- compare incoming value against `ADMIN_REFRESH_TOKEN`

Recommended request header:
- `X-Admin-Token: <token>`

---

## 7. Shared response conventions

## 7.1 Success responses

Successful responses should use:
- HTTP 200 for normal reads
- HTTP 202 for accepted async/scheduled trigger actions when appropriate

## 7.2 Error responses

Error responses should be structured.

Recommended error shape:

~~~json
{
  "error": {
    "code": "string_code",
    "message": "Human-readable error message"
  }
}
~~~

Example:

~~~json
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid admin token."
  }
}
~~~

## 7.3 Null-safe behavior

If same-day summary is not yet available, prefer one of:
- a response with explicit null fields and availability status
- or a 404 only if the frontend is designed for that behavior

For this project, explicit availability metadata is preferred over hard failure where practical.

---

## 8. Endpoint: GET /api/health

## Purpose

Return a lightweight backend health status for container health checks and operational verification.

## Request

No request body.

## Response example

~~~json
{
  "status": "ok",
  "service": "backend",
  "environment": "production",
  "time": "2026-04-12T08:30:00Z",
  "database": "ok"
}
~~~

## Response fields

- `status`: string, expected value `ok`
- `service`: string, backend service identifier
- `environment`: string, such as `development` or `production`
- `time`: ISO 8601 timestamp
- `database`: string, `ok` when a lightweight database query succeeds, otherwise `unavailable`

## Status codes

- `200 OK`
- `503 Service Unavailable` if the backend is alive but the database connectivity check fails

## Operational use

Recommended uses:

- Docker Compose backend health check
- external uptime monitor target through Nginx at `http://118.178.195.6:<APP_PORT>/api/health`
- post-deploy smoke check before validating the homepage

The endpoint is intentionally lightweight and should not depend on GLM5, worker progress, or news freshness. It answers backend reachability plus database connectivity only.

---

## 9. Endpoint group: Product tracking

The product-tracking endpoints support a manually curated event library for specific biopharma products. A tracked product is created explicitly by a user, then backfilled from existing news plus targeted Google News RSS queries. GLM5 is used at the service boundary to decide product relevance and extract structured milestone events.

### `GET /api/products`

Returns the list of tracked products.

Query params:
- `q` optional substring filter on display name or company name

Response shape:

~~~json
{
  "items": [
    {
      "id": 1,
      "slug": "cb-010",
      "display_name": "CB-010",
      "company_name": "Caribou Biosciences",
      "aliases": ["CB010"],
      "indications": ["NHL"],
      "modality": "allogeneic CAR-T",
      "status": "active",
      "timeline_event_count": 5,
      "linked_news_count": 12,
      "last_backfill_at": "2026-04-17T10:00:00Z",
      "updated_at": "2026-04-17T10:00:00Z"
    }
  ]
}
~~~

### `POST /api/products`

Creates a tracked product and immediately attempts a synchronous backfill.

Request body:

~~~json
{
  "display_name": "CB-010",
  "company_name": "Caribou Biosciences",
  "aliases": ["CB010"],
  "indications": ["NHL"],
  "modality": "allogeneic CAR-T"
}
~~~

Response:
- `201 Created`
- returns product detail with latest timeline event and linked news preview

### `GET /api/products/{slug}`

Returns one tracked product with summary metadata, latest timeline event, and a preview set of linked news items.

### `GET /api/products/{slug}/timeline`

Returns the full structured timeline for a tracked product.

### `GET /api/products/{slug}/sources`

Returns the linked source news items used for product tracking.

### `POST /api/products/{id}/backfill`

Re-runs the product backfill pipeline for one tracked product.

Response shape:

~~~json
{
  "accepted": true,
  "product_id": 1,
  "product_slug": "cb-010",
  "fetched_candidates": 6,
  "linked_news_count": 14,
  "created_timeline_events": 2,
  "updated_at": "2026-04-17T10:05:00Z"
}
~~~

Operational notes:
- Backfill uses public RSS search plus existing stored news.
- Event dates are normalized to UTC.
- Timeline extraction is structured JSON only; empty extraction is valid.

---

## 10. Endpoint: GET /api/categories

## Purpose

Return the fixed category list used across the application.

This keeps frontend filters and backend taxonomy aligned.

## Request

No request body.

## Response example

~~~json
{
  "categories": [
    "Financing",
    "Clinical/Regulatory Progress",
    "R&D",
    "Partnership/Licensing",
    "M&A/Organization",
    "Manufacturing/CMC",
    "Policy/Industry Environment",
    "Other"
  ]
}
~~~

## Response fields

- `categories`: array of strings

## Status codes

- `200 OK`

---

## 11. Endpoint: GET /api/news

## Purpose

Return a paginated list of normalized news items for feed display.

## Query parameters

### `page`
- type: integer
- required: no
- default: `1`
- minimum: `1`

### `page_size`
- type: integer
- required: no
- default: `20`
- recommended maximum: `100`

### `category`
- type: string
- required: no
- allowed values:
  - `Financing`
  - `Clinical/Regulatory Progress`
  - `R&D`
  - `Partnership/Licensing`
  - `M&A/Organization`
  - `Manufacturing/CMC`
  - `Policy/Industry Environment`
  - `Other`

### `date`
- type: string
- required: no
- format: `YYYY-MM-DD`
- meaning: return items associated with that calendar date according to backend date selection logic

### `q`
- type: string
- required: no
- purpose: optional lightweight text filtering, typically title/source-level for MVP
- note: this can remain unimplemented in the first build if clearly documented

### `sort`
- type: string
- required: no
- default: `published_at_desc`
- allowed MVP values:
  - `published_at_desc`
  - `published_at_asc`

## Behavior

If no category is provided, return all categories.

If no date is provided, default to current reporting date or recent items, according to implementation choice.  
For MVP, returning most recent items first is recommended.

## Response example

~~~json
{
  "items": [
    {
      "id": 101,
      "title": "Example biotech raises Series B financing for cell therapy platform",
      "canonical_url": "https://example.com/news/series-b-cell-therapy",
      "source_name": "Example Source",
      "published_at": "2026-04-12T06:45:00Z",
      "category": "Financing",
      "short_summary": "The company announced a Series B round to expand its cell therapy platform and manufacturing capabilities.",
      "image_url": "https://example.com/image.jpg",
      "language": "en",
      "entities": ["Example Biotech"],
      "importance_score": 0.86,
      "relevance_to_cell_therapy": 0.95
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 125,
    "total_pages": 7
  },
  "filters": {
    "category": null,
    "date": "2026-04-12",
    "q": null,
    "sort": "published_at_desc"
  },
  "last_updated_at": "2026-04-12T08:30:00Z"
}
~~~

## Response fields

### `items`
Array of news item objects.

Each item should include:

- `id`: integer or string identifier
- `title`: string
- `canonical_url`: string
- `source_name`: string
- `published_at`: ISO 8601 timestamp
- `category`: string from allowed category list
- `short_summary`: string
- `image_url`: string or null
- `language`: string or null
- `entities`: array of strings or null
- `importance_score`: number or null
- `relevance_to_cell_therapy`: number or null

### `pagination`
Object containing:
- `page`
- `page_size`
- `total_items`
- `total_pages`

### `filters`
Echo of applied filters:
- `category`
- `date`
- `q`
- `sort`

### `last_updated_at`
Timestamp of most recent successful relevant update known to the backend.

## Status codes

- `200 OK`
- `400 Bad Request` for invalid query parameters

## Example invalid category error

~~~json
{
  "error": {
    "code": "invalid_category",
    "message": "Unsupported category value."
  }
}
~~~

---

## 11. Endpoint: GET /api/news/today-summary

## Purpose

Return the stored daily summary block for homepage rendering.

This summary is generated by the worker using processed same-day news items and GLM5 enrichment where available.
If fewer than three same-day items are stored, the Phase 4 MVP may include the latest stored processed items as a controlled fallback so the dashboard remains informative after source feeds publish outside the local reporting date. The summary remains generated only from persisted, processed database records.

## Query parameters

### `date`
- type: string
- required: no
- format: `YYYY-MM-DD`
- default: current reporting date

## Response example when summary exists

~~~json
{
  "available": true,
  "summary_date": "2026-04-12",
  "daily_summary": "Cell therapy and broader biotech news today were led by financing updates, clinical progress, and manufacturing-related announcements.",
  "top_events": [
    {
      "title": "Example biotech raises Series B financing",
      "category": "Financing",
      "canonical_url": "https://example.com/news/series-b-cell-therapy"
    },
    {
      "title": "Company reports early clinical update",
      "category": "Clinical/Regulatory Progress",
      "canonical_url": "https://example.com/news/clinical-update"
    }
  ],
  "trend_signal": "Financing and execution-focused updates were more prominent than policy developments today.",
  "category_counts": {
    "Financing": 4,
    "Clinical/Regulatory Progress": 3,
    "R&D": 5,
    "Partnership/Licensing": 2,
    "M&A/Organization": 1,
    "Manufacturing/CMC": 2,
    "Policy/Industry Environment": 1,
    "Other": 0
  },
  "model_name": "glm5",
  "generated_at": "2026-04-12T08:20:00Z"
}
~~~

## Response example when summary is not yet available

~~~json
{
  "available": false,
  "summary_date": "2026-04-12",
  "daily_summary": null,
  "top_events": [],
  "trend_signal": null,
  "category_counts": {},
  "model_name": null,
  "generated_at": null
}
~~~

## Response fields

- `available`: boolean
- `summary_date`: string in `YYYY-MM-DD`
- `daily_summary`: string or null
- `top_events`: array
- `trend_signal`: string or null
- `category_counts`: object
- `model_name`: string or null
- `generated_at`: ISO 8601 timestamp or null

## Top event object fields

Each element in `top_events` should include at least:
- `title`
- `category`
- `canonical_url`

Optional:
- `source_name`
- `published_at`
- `short_summary`

## Status codes

- `200 OK`
- `400 Bad Request` for invalid date format

---

## 12. Endpoint: POST /api/admin/refresh

## Purpose

Trigger a manual ingestion/refresh workflow.

This should be treated as an admin-only operational endpoint.

## Authentication

Require header:

- `X-Admin-Token: <ADMIN_REFRESH_TOKEN>`

## Request body

For MVP, the request body may be empty.

Optional future request body:

~~~json
{
  "mode": "full"
}
~~~

Possible future modes:
- `full`
- `summary_only`
- `source_subset`

For the first version, bodyless trigger is acceptable.

## Behavior

This endpoint should not block until the whole ingestion pipeline finishes if the run may be long.

Recommended behavior:
- accept request
- enqueue or trigger worker-side logic
- return accepted status and metadata

Phase 4 behavior:
- validates `X-Admin-Token` against `ADMIN_REFRESH_TOKEN`
- runs the same ingestion cycle used by the worker when the token is configured and valid
- uses the same default GLM5 endpoint and ingestion timeout settings as the worker when `.env` does not override them
- rejects overlapping manual refreshes in the same backend process with `409 Conflict`
- returns `503 Service Unavailable` if the admin token is not configured
- returns a compact accepted response containing run counts in the message

## Response example

~~~json
{
  "accepted": true,
  "message": "Refresh completed. Fetched 8, inserted 8, updated 0, duplicates 0.",
  "requested_at": "2026-04-12T08:35:00Z"
}
~~~

## Error example: unauthorized

~~~json
{
  "error": {
    "code": "unauthorized",
    "message": "Invalid admin token."
  }
}
~~~

## Status codes

- `202 Accepted`
- `401 Unauthorized`
- `409 Conflict` if a manual refresh is already running in the backend process
- `503 Service Unavailable` when admin refresh is intentionally unavailable because no token is configured
- `500 Internal Server Error`

---

## 13. Optional future endpoint: GET /api/news/{id}

## Purpose

Return a single news item in greater detail.

This endpoint is not required for the MVP homepage, but it is a natural extension if a detail page is later added.

## Response example

~~~json
{
  "id": 101,
  "title": "Example biotech raises Series B financing for cell therapy platform",
  "canonical_url": "https://example.com/news/series-b-cell-therapy",
  "source_name": "Example Source",
  "published_at": "2026-04-12T06:45:00Z",
  "category": "Financing",
  "short_summary": "The company announced a Series B round to expand its cell therapy platform and manufacturing capabilities.",
  "content_text": "Normalized content text stored for internal processing.",
  "image_url": "https://example.com/image.jpg",
  "language": "en",
  "entities": ["Example Biotech"],
  "importance_score": 0.86,
  "relevance_to_cell_therapy": 0.95,
  "created_at": "2026-04-12T08:00:00Z",
  "updated_at": "2026-04-12T08:10:00Z"
}
~~~

## Status codes

- `200 OK`
- `404 Not Found`

---

## 14. Backend schema guidance

FastAPI response models should be explicit.

Recommended schema groups:
- `HealthResponse`
- `CategoriesResponse`
- `NewsItemResponse`
- `NewsListResponse`
- `TodaySummaryResponse`
- `RefreshAcceptedResponse`
- `ErrorResponse`

This keeps route behavior predictable and improves validation.

Phase 4 persistence note:
- `GET /api/news` and `GET /api/news/today-summary` read from PostgreSQL-backed tables.
- The backend creates the initial MVP tables at startup.
- The worker ingests a small RSS source set, normalizes items, deduplicates by canonical URL, normalized title hash, and a conservative near-duplicate title check, classifies/enriches items, and stores the daily summary.
- Daily summary top events are strictly validated structured objects before JSON persistence.
- Deterministic sample seeding is disabled by default and only runs when `SEED_SAMPLE_DATA=true`.
- This startup initialization is intentionally lightweight and should be replaced or complemented by migrations when schema changes become frequent.

---

## 15. Validation rules

## 15.1 Category validation
Any returned category must be one of the fixed allowed values.

## 15.2 URL validation
`canonical_url` should be a valid normalized source URL.

## 15.3 Summary validation
`short_summary` and `daily_summary` should be non-empty when marked available.

## 15.4 Pagination validation
- `page >= 1`
- `1 <= page_size <= 100`

## 15.5 Date validation
Date query parameters should follow:
- `YYYY-MM-DD`

Invalid dates should produce `400 Bad Request`.

---

## 16. Error code recommendations

Recommended error codes include:

- `bad_request`
- `invalid_date`
- `invalid_category`
- `unauthorized`
- `not_found`
- `internal_error`
- `service_unavailable`

These are recommendations, not a mandatory exhaustive list.

---

## 17. Frontend integration notes

The frontend is expected to use:

- `GET /api/categories` to populate filters
- `GET /api/news` to render the feed
- `GET /api/news/today-summary` to render the summary module

Suggested homepage loading pattern:
1. load summary
2. load categories
3. load first page of news
4. update filters client-side via repeated `GET /api/news` calls

---

## 18. Versioning

For the MVP, explicit API versioning in the route path is optional.

Possible future path:
- `/api/v1/...`

If versioning is introduced later, update:
- route definitions
- Nginx expectations if needed
- frontend fetch paths
- documentation

---

## 19. Summary

The MVP API is intentionally small.

Core routes:
- `GET /api/health`
- `GET /api/categories`
- `GET /api/news`
- `GET /api/news/today-summary`
- `POST /api/admin/refresh`

These routes are sufficient to support:
- homepage rendering
- category filtering
- operational health checks
- manual refresh triggering
