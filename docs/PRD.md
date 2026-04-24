# PRD.md

# Product Requirements Document
## Project name
Biomed / Cell Therapy Daily Intelligence Dashboard

## 1. Product overview

This project is a web application for daily tracking of news in biomedicine, biotech, pharma, and especially cell therapy-related domains.

The app will:
- collect daily news from selected public sources
- normalize and deduplicate news items
- classify them into fixed business categories
- generate a daily summary using the server-side GLM5 endpoint
- display the results in a masonry-style responsive web interface
- run behind a single Nginx public port on the target server

The initial goal is a practical MVP that works reliably every day. This is not a full-scale media platform and not a generalized search engine.

---

## 2. Product goals

### Primary goals
1. Provide a daily, structured, high-signal overview of relevant industry news.
2. Make it easy to scan many news items quickly.
3. Surface key trends and important events through a model-generated daily summary.
4. Keep the deployment simple and production-like.

### Secondary goals
1. Build a foundation for future search, filtering, alerting, and historical analysis.
2. Support future entity-level aggregation such as companies, technologies, and therapeutic areas.
3. Support future push channels such as email digest or messaging bots.

---

## 3. Non-goals for MVP

The following are explicitly out of scope for the first version unless later requested:
- user accounts and login
- personalized recommendation
- comments or social interactions
- full-text semantic search
- multilingual translation workflow
- analyst-written manual editorial backend
- RAG over internal proprietary documents
- complex trend charts
- mobile native app

---

## 4. Target users

### Primary users
- researchers following biomedical and translational developments
- biotech / cell therapy industry watchers
- internal lab or team members who want a daily external news overview

### User needs
- know what happened today
- quickly identify relevant financing / clinical / R&D / BD events
- browse source-linked news in a clean interface
- get a concise summary instead of reading every article in full

---

## 5. User stories

### Daily browsing
- As a user, I want to open the homepage and immediately see the most important industry events of the day.
- As a user, I want to skim news cards quickly without opening every source page.
- As a user, I want to filter by category to focus on the types of events I care about.

### Summary consumption
- As a user, I want a concise daily summary that highlights the most important developments.
- As a user, I want the summary to be factual and not promotional.

### Reliability
- As an operator, I want the ingestion pipeline to run safely multiple times per day.
- As an operator, I want duplicate news items to be minimized.
- As an operator, I want the app to keep serving even if one ingestion source fails.

---

## 6. MVP scope

### Included in MVP
1. Homepage
2. Daily summary module
3. Category filter module
4. Masonry-style news feed
5. Source links to original articles
6. Scheduled ingestion worker
7. Deduplication
8. Fixed category classification
9. Deployment with Docker Compose
10. Nginx single-port reverse proxy

### Optional but acceptable if low effort
- basic manual refresh endpoint
- small status badge for last update time
- source favicon or lightweight source label styling
- simple keyword search over titles only

---

## 7. Functional requirements

## 7.1 Homepage
The homepage must include:
- product title
- current date or reporting date
- last successful update time
- refresh / ingestion status
- daily summary block
- category filters
- masonry news feed

## 7.2 Daily summary module
The daily summary module must:
- summarize the day in concise analyst-style wording
- include 3 to 5 key events
- be generated from same-day processed news items, with a controlled latest-item fallback if same-day feed volume is too sparse
- be stored and served from backend API
- degrade gracefully if summary generation fails

## 7.3 Category filtering
The UI must support these fixed categories:
- Financing
- Clinical/Regulatory Progress
- R&D
- Partnership/Licensing
- M&A/Organization
- Manufacturing/CMC
- Policy/Industry Environment
- Other

The user must be able to filter the feed by one category or view all.

## 7.4 News cards
Each card should display:
- title
- source
- publish time
- category tag
- short summary
- original article link

Optional:
- image thumbnail if reliable

The card must not require image presence to render correctly.

## 7.5 News ingestion
The system must:
- fetch from selected public sources
- extract candidate articles
- normalize title, URL, source, time, and content text
- deduplicate items
- classify items
- summarize items
- store items in PostgreSQL

Phase 4 status:
- PostgreSQL-backed tables and API reads are in place
- the worker ingests a small audited RSS source set and persists normalized items
- deterministic rule classification runs before GLM5 refinement for ambiguous items
- GLM5 output is validated before persistence and falls back safely when unavailable
- daily summary event objects are validated before storage

## 7.6 Manual refresh
The system should expose an admin refresh endpoint for manual pipeline triggering.

Phase 4 status:
- the endpoint validates `X-Admin-Token`
- valid requests run a bounded ingestion cycle synchronously and return compact run counts
- overlapping manual refreshes in the same backend process return a conflict response

## 7.7 Scheduling
The system should run the ingestion pipeline multiple times per day.

Recommended schedule for MVP:
- morning main run
- midday supplementary run
- evening supplementary run

---

## 8. Non-functional requirements

### Performance
- homepage should remain responsive under normal daily item volume
- initial render should not block on image availability
- feed rendering should remain smooth on desktop and mobile

### Reliability
- one failed source should not crash the whole ingestion run
- worker failures should not crash frontend or backend API
- repeated runs should be idempotent where possible

### Maintainability
- clear separation between frontend, backend, worker, and infra
- structured schemas for model outputs
- source traceability retained for every news item

### Security
- only Nginx exposes a public port
- secrets are loaded from environment variables
- database is internal to Docker network

---

## 9. Success metrics

### MVP success criteria
1. The app successfully updates on schedule.
2. The homepage shows same-day categorized news, or the latest processed database-backed items when same-day feed volume is too sparse.
3. The daily summary is generated successfully on most runs.
4. Duplicate stories are acceptably controlled.
5. The app is accessible through a single public port and survives container restarts.

### Quality indicators
- low visible duplicate rate
- meaningful categorization accuracy
- daily summary readability
- stable deployment and restart behavior

---

## 10. Data model expectations

### News item
Core fields:
- id
- title
- canonical_url
- source_name
- published_at
- category
- short_summary
- content_text
- image_url
- language
- title_hash
- created_at
- updated_at

Optional enrichment fields:
- entities
- importance_score
- relevance_to_cell_therapy

### Daily summary
Core fields:
- id
- summary_date
- daily_summary
- top_events
- trend_signal
- category_counts
- model_name
- generated_at

---

## 11. API expectations

Minimum API surface for MVP:
- GET /api/news
- GET /api/news/today-summary
- GET /api/categories
- POST /api/admin/refresh

Optional later:
- GET /api/news/{id}
- GET /api/sources
- GET /api/health

---

## 12. UX principles

- information-first
- compact but readable
- calm and credible
- low visual noise
- quick scanning over decorative presentation

This product should feel like a daily research / market intelligence dashboard, not a marketing landing page and not a generic news portal.

---

## 13. Risks

1. Source structures may change unexpectedly.
2. Duplicate syndicated articles may still appear without stronger similarity logic.
3. LLM outputs may become malformed or inconsistent without strict schema validation.
4. Overly broad source expansion may reduce signal quality.

---

## 14. Future roadmap

Potential future features:
- keyword search
- company/entity pages
- saved filters
- weekly summary page
- email digest
- historical trend views
- tagging by modality, disease area, or company type
- source management panel
- richer admin controls
