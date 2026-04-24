# AGENTS.md

## Project mission

Build a production-style web application that collects, classifies, summarizes, and displays daily news in biomedicine and cell therapy.

The app must:
- collect daily news from reliable public sources
- classify each item into a fixed business category
- generate a daily summary using the lab/server-side GLM5 endpoint
- present news in a responsive masonry-style feed
- run behind Nginx on a single public port
- deploy with Docker Compose

This repository is for a practical MVP first, then iterative enhancement.

---

## Fixed architecture

Do not change these choices unless explicitly asked.

- Frontend: Next.js + TypeScript + Tailwind + shadcn/ui
- Backend API: FastAPI + Pydantic
- Worker: separate Python process for scheduled ingestion and summarization
- Database: PostgreSQL
- Reverse proxy: Nginx
- Runtime / deployment: Docker Compose
- Model summarization: server-side GLM5 endpoint already available in the target environment

Do not replace this stack with Flask, Django templates, pure PHP, Supabase-first architecture, or a monolithic all-in-one server.

---

## Product requirements

The homepage must contain these modules:

1. Header
- product/app title
- current date
- last updated time
- refresh status

2. Daily summary module
- one concise daily overview generated from GLM5
- 3 to 5 key events
- neutral, analyst-style wording
- no exaggerated claims

3. Category filter module
Supported categories:
- Financing
- Clinical/Regulatory Progress
- R&D
- Partnership/Licensing
- M&A/Organization
- Manufacturing/CMC
- Policy/Industry Environment
- Other

4. News feed
- masonry / waterfall style layout
- each card contains title, source, publish time, category tag, short summary, original link
- responsive: desktop multi-column, tablet 2 columns, mobile 1 column

---

## Core engineering principles

- Prefer a stable MVP over feature breadth.
- Prefer simple, maintainable patterns over clever abstractions.
- Keep responsibilities separated: frontend, API, worker, and deployment config.
- Make all ingestion jobs idempotent.
- Make all LLM outputs structured and validated before persistence.
- Keep API routes thin; place business logic in service modules.
- Store timestamps in UTC internally; format for display in frontend.
- Every externally visible field must be traceable to source data or validated model output.
- Do not silently invent product requirements.

---

## Expected repository structure

- AGENTS.md at repo root for shared project rules
- .agents/skills/* for repo-scoped skills
- frontend/ for Next.js app
- backend/ for FastAPI app and worker
- infra/nginx for reverse proxy config
- docs/ for PRD, architecture, API, and deployment notes

When changing architecture or folder conventions, update docs in the same task.

---

## Working style for Codex

For any non-trivial task:
1. inspect existing structure first
2. state a brief implementation plan
3. implement with minimal necessary changes
4. run the relevant checks
5. summarize changed files and remaining risks

When a task is ambiguous, preserve the current architecture and make the smallest safe decision consistent with this file.

Do not introduce major new dependencies unless they clearly simplify the current architecture.

---

## Frontend rules

- Use Next.js App Router.
- Default to server components unless client interactivity is required.
- Use TypeScript everywhere.
- Use Tailwind utilities and shadcn/ui primitives.
- Keep the visual style clean, information-dense, and calm.
- Avoid loud gradients, glassmorphism, heavy animations, or marketing-style hero sections.
- Prefer small, composable components.
- Do not hardcode backend hostnames in UI components.
- Read API base URL from environment/config only.
- Keep loading, empty, and error states explicit.
- Preserve accessibility: semantic markup, keyboard navigation, sufficient contrast, descriptive labels.

### Visual direction

Target style:
- modern research/market intelligence dashboard
- light background
- restrained accent color
- compact but readable cards
- strong hierarchy for title, source, time, and category
- data product feel, not a hospital brochure and not a flashy media portal

---

## Masonry feed rules

- Feed order should be deterministic, usually newest first.
- Card heights may differ, but alignment should remain visually clean.
- Prefer simple, robust implementations before heavy libraries.
- Preserve responsive behavior and scroll performance.
- Do not block initial rendering on images.
- Use graceful skeleton states while loading.

---

## Backend rules

- Use FastAPI routers for HTTP layer.
- Use Pydantic schemas for request/response contracts.
- Put data access and business logic in services/modules, not directly in route functions.
- Keep model integrations isolated behind service functions.
- Normalize source data before classification and summary generation.
- Persist dedupe keys.
- Add logging around ingestion, classification, summarization, and DB writes.
- Avoid hidden side effects in import time.

### API expectations

Expose at least:
- GET /api/news
- GET /api/news/today-summary
- GET /api/categories
- POST /api/admin/refresh

Keep response payloads explicit and typed.

---

## News ingestion rules

The ingestion pipeline must follow this order:
1. fetch source page / feed
2. extract candidate items
3. normalize title, URL, source, publish time, content text
4. deduplicate
5. classify
6. summarize/enrich
7. store
8. surface in API

Use a hybrid dedupe strategy:
- canonical URL
- normalized title hash
- optional near-duplicate title/content check when needed

Do not create duplicate rows for the same event unless a product requirement explicitly calls for source-level duplication.

Favor reliable public sources first. Do not optimize for maximum source count in the MVP.

---

## Classification rules

Use the fixed category taxonomy defined above.

Preferred strategy:
- deterministic keyword / rule pass first
- LLM refinement second for ambiguous items
- validate against allowed category list before saving

Do not invent new categories without updating:
- frontend filter UI
- backend schema
- docs
- relevant skill instructions

---

## GLM5 summarization rules

All GLM5 outputs must be structured JSON at the service boundary.

For single-news enrichment, prefer fields like:
- one_line_summary
- category
- entities
- importance_score
- relevance_to_cell_therapy

For daily summary, prefer fields like:
- daily_summary
- top_events
- trend_signal
- category_counts

Validate output before persistence.
On validation failure:
- retry once with stricter instruction
- then fall back to a safe deterministic summary path or leave explicit null/error state

Do not store raw, unvalidated free-form model output as if it were trusted structured data.

---

## Deployment rules

- Use Docker Compose as the primary run/deploy path.
- Use Nginx as the single public entrypoint.
- Expose one public port only from Nginx.
- Frontend and backend should communicate over the internal Docker network.
- Use environment variables from .env files; never hardcode secrets.
- Add health checks where practical.
- Keep deployment docs updated when ports, services, or env vars change.

Do not switch the primary deployment model to systemd-only or manual multi-terminal startup.

---

## Testing and validation

Before considering a task done, run the relevant checks.

Minimum expectations:
- frontend lint/build when frontend changes
- backend tests and/or import/runtime checks when backend changes
- docker compose config validation when infra changes

If no formal test exists yet, add the smallest meaningful validation for the touched area.

---

## Documentation rules

When behavior, architecture, APIs, environment variables, or deployment steps change, update docs in docs/ within the same task.

At minimum keep these docs aligned:
- docs/PRD.md
- docs/ARCHITECTURE.md
- docs/API_SPEC.md
- docs/DEPLOYMENT.md

---

## Definition of done

A task is done only when:
- code matches the fixed architecture
- relevant checks pass or failures are explicitly explained
- changed behavior is reflected in docs when needed
- no placeholder mocks remain in production paths unless clearly marked as temporary
- the result is reviewable and runnable by another developer

