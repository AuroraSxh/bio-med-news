# Changes Log — 2026-04-12

This document records all modifications made to the biomed-news-app project during this session, for Codex reference.

---

## 1. Frontend: Dashboard Full Rewrite

**File:** `frontend/components/dashboard.tsx`

### Added Features

| Feature | Description |
|---------|-------------|
| Pagination | Prev/Next buttons + page number bar (up to 7 visible pages with smart windowing). State `currentPage` added. |
| Search | Debounced (400ms) search input with magnifying glass icon. Wired to backend `q` parameter. States `searchQuery` / `activeSearch` added. |
| Date Picker | `<input type="date">` next to daily summary heading. Enables browsing historical summaries via `?date=YYYY-MM-DD`. State `selectedDate` added. |
| Row-major Grid Layout | Replaced CSS `columns` (which flows top-to-bottom per column) with `grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3` for natural left-to-right reading order. |
| Category Counts | Filter buttons display **real database counts** from `news.category_counts` (not GLM5 summary counts). |
| Image Thumbnails | Cards render `image_url` as a 160px header image with `loading="lazy"` and error-hiding via `onError`. |
| Entity Badges | Up to 5 extracted entities shown as small tags below card summary, with `+N` overflow indicator. |
| Relevance Indicator | "High relevance" badge displayed on cards where `relevance_to_cell_therapy >= 0.7`. |
| Summary Date Formatting | Raw ISO date `2026-04-12` now displays as `April 12, 2026` via `formatDate()`. |
| Top Event Details | Each top event now shows `source_name` and `published_at` in addition to title and category. |
| Trend Signal Styling | Trend signal gets a dedicated highlighted box with teal background. |
| Selective Re-fetching | Categories & summary fetch independently from news items — category/page/search changes only re-fetch `/api/news`. |
| Horizontal Scroll Filters | Category filter bar uses `overflow-x-auto` with thin scrollbar on mobile instead of wrapping to many rows. |
| Footer | Added footer with data source attribution and update frequency info. |
| Hover Effects | Cards gain shadow on hover (`hover:shadow-md`), top events highlight on hover. |

### Architecture Change

Previously all 3 API calls (`/categories`, `/news/today-summary`, `/news`) were bundled in a single `useEffect`. Now split into two independent effects:
- **Meta effect** (categories + summary): triggers on `reloadKey` and `selectedDate`
- **News effect** (news items): triggers on `selectedCategory`, `activeSearch`, `currentPage`, `selectedDate`, `reloadKey`

This eliminates redundant API calls when only filters change.

---

## 2. Frontend: CSS Animations & Dark Mode

**File:** `frontend/app/globals.css`

| Addition | Description |
|----------|-------------|
| `@keyframes fade-in` | Cards fade in with 8px upward slide, 0.35s ease-out |
| `.animate-fade-in` stagger | Grid children get staggered animation delays (0ms to 240ms) |
| `.scrollbar-thin` | Thin 4px scrollbar for horizontal category filter bar (webkit + Firefox) |
| `animate-pulse` | Added to skeleton loading elements |
| `color-scheme: light dark` | Supports both color schemes |
| `dark:` body styles | `dark:bg-slate-900 dark:text-slate-100` via `@apply` |
| Dark scrollbar | `.dark .scrollbar-thin` with slate-500 thumb |

---

## 3. Frontend: Dark Mode (Full Implementation)

### Files changed:

| File | Changes |
|------|---------|
| `frontend/tailwind.config.ts` | Added `darkMode: "class"` |
| `frontend/app/layout.tsx` | Added `suppressHydrationWarning`, inline `<script>` for theme init from localStorage / `prefers-color-scheme` |
| `frontend/components/theme-toggle.tsx` | **New file.** Sun/moon toggle button, persists to localStorage, respects system preference |
| `frontend/components/dashboard.tsx` | `dark:` variants on all elements (backgrounds, borders, text, inputs, cards, badges) |
| `frontend/components/ui/card.tsx` | `dark:bg-slate-800 dark:border-slate-700` on Card, `dark:border-slate-700` on CardHeader |
| `frontend/components/ui/button.tsx` | Dark variants for default (`dark:bg-teal-600`) and outline (`dark:bg-slate-800`) |
| `frontend/components/ui/badge.tsx` | Dark variants for default, secondary, outline variants |
| `frontend/components/skeleton-card.tsx` | `dark:bg-slate-700` on all skeleton placeholders |

---

## 4. Frontend: Favicon & Open Graph

**File:** `frontend/app/layout.tsx`

- Added `export const viewport: Viewport` with `width: "device-width", initialScale: 1`
- Added OpenGraph metadata (`title`, `description`, `type`, `siteName`)
- Added Twitter card metadata (`summary`)
- Added `icons: { icon: "/favicon.svg" }`

**File:** `frontend/public/favicon.svg` — **New file.** Teal DNA double-helix SVG icon.

---

## 5. Frontend: Category Summaries + Left-Right Interaction

**File:** `frontend/components/dashboard.tsx`

### Daily Summary Enhancement

- **Refresh button**: Circular arrow icon button in CardHeader, triggers `reloadKey++` to re-fetch summary data
- **Category summaries display**: Below the overall `daily_summary` text, renders each `category_summaries` entry as a styled block (category name heading + summary text)
- **Left-right interaction**: State `selectedSummaryCategory` added
  - Each category summary block is a `<button>` — clicking highlights it (teal border + ring)
  - Right-side top events filter to show only events matching the selected category
  - Header dynamically changes: "Top events" → "R&D events"
  - Click again to deselect; "Show all" link appears when filtered
  - Empty state: "No top events for this category."

**File:** `frontend/lib/types.ts`
- `TodaySummaryResponse` added: `category_summaries: Record<string, string>`

---

## 6. Backend: ILIKE Wildcard Escaping (Security Fix)

**File:** `backend/app/services/news_repository.py`

**Before:**
```python
needle = f"%{q}%"
filters.append(or_(NewsItem.title.ilike(needle), NewsItem.source_name.ilike(needle)))
```

**After:**
```python
escaped_q = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
needle = f"%{escaped_q}%"
filters.append(or_(
    NewsItem.title.ilike(needle, escape="\\"),
    NewsItem.source_name.ilike(needle, escape="\\"),
    NewsItem.short_summary.ilike(needle, escape="\\"),
))
```

**Also expanded search scope**: Added `short_summary` to the ILIKE `or_()` clause (#15 fix).

---

## 7. Backend: Timing-Safe Admin Token Comparison (Security Fix)

**File:** `backend/app/api/routes.py`

**Before:**
```python
if x_admin_token != configured_token:
```

**After:**
```python
import hmac
if not hmac.compare_digest(x_admin_token or "", configured_token):
```

---

## 8. Backend: API Rate Limiting

**File:** `backend/app/main.py`
- Added `slowapi` middleware: `Limiter`, `SlowAPIMiddleware`, `SlowAPIErrorHandler`

**File:** `backend/app/api/routes.py`
- All public endpoints (`/health`, `/categories`, `/news`, `/news/today-summary`): `@limiter.limit("60/minute")`
- Admin endpoint (`/admin/refresh`): `@limiter.limit("5/minute")`
- Added `request: Request` parameter to all route functions (required by slowapi)

**File:** `backend/pyproject.toml`
- Added dependency: `slowapi>=0.1.9,<0.2.0`

---

## 9. Backend: Real Category Counts in News API

**File:** `backend/app/services/news_repository.py`

`list_news()` now returns `category_counts` — a `GROUP BY category` query from the database. Applies date/search filters but NOT the category filter, so counts show "how many items per category" regardless of which category is currently selected.

**File:** `backend/app/schemas/responses.py`
- `NewsListResponse` added: `category_counts: dict[str, int] = {}`

**File:** `frontend/lib/types.ts`
- `NewsListResponse` added: `category_counts: Record<string, number>`

**Frontend change:** Category filter buttons now use `news.category_counts` (real DB counts) instead of `summary.category_counts` (GLM5 estimate).

---

## 10. Backend: GLM5 Category Summaries

### Prompt Change

**File:** `backend/app/services/glm5_client.py`
- `summarize_day()` prompt now requires `category_summaries` key:
  ```
  "category_summaries must be a dict where each key is a category name
   that has items, and the value is a 1-2 sentence summary of that
   category's key developments today."
  ```

### Data Model

**File:** `backend/app/schemas/pipeline.py`
- `DailySummaryDraft` added: `category_summaries: dict[str, str] = Field(default_factory=dict)`
- `daily_summary` max_length increased: 1400 → 2000

**File:** `backend/app/models/news.py`
- `DailySummary` model added column: `category_summaries: Mapped[dict[str, str] | None] = mapped_column(JSONType, nullable=True)`

**File:** `backend/app/schemas/responses.py`
- `TodaySummaryResponse` added: `category_summaries: dict[str, str] = {}`

### Storage & Retrieval

**File:** `backend/app/services/news_repository.py`
- `upsert_daily_summary()`: stores `draft.category_summaries`
- `get_today_summary()`: returns `summary.category_summaries or {}`

### Fallback

**File:** `backend/app/services/summary.py`
- `_normalize_summary()`: passes through `draft.category_summaries`
- `_fallback_summary()`: generates per-category fallback text from item titles

### Database Migration (manual)
```sql
ALTER TABLE daily_summaries ADD COLUMN IF NOT EXISTS category_summaries JSONB;
```

---

## 11. Backend: GLM5 Timeout Increase

**Files:** `.env`, `backend/app/core/config.py`
- `GLM5_REQUEST_TIMEOUT_SECONDS`: `60` → `300` (5 minutes)
- Prevents timeout for daily summary generation which calls GLM5 with large payloads

---

## 12. Backend: Alembic Migration System

**File:** `backend/pyproject.toml` — Added `alembic>=1.13.0,<2.0.0`

**New files:**
- `backend/alembic.ini` — Config with `script_location = alembic`
- `backend/alembic/env.py` — Reads `DATABASE_URL` from env, imports `Base` from `app.db`, normalizes `postgresql://` to `postgresql+psycopg://`
- `backend/alembic/script.py.mako` — Standard migration template
- `backend/alembic/versions/.gitkeep`

**File:** `backend/app/services/database_init.py`
- Added comment: `# For production, prefer: alembic upgrade head`

---

## 13. Backend: Unit Tests

**File:** `backend/pyproject.toml` — `[tool.pytest.ini_options]` already present

**New files (35 tests, all passing):**

| File | Tests |
|------|-------|
| `backend/tests/__init__.py` | Empty |
| `backend/tests/test_sources.py` | `canonicalize_url()` (8 tests), `clean_text()` (6 tests) |
| `backend/tests/test_ingestion.py` | `dedupe_candidates()` (7 tests) — URL, hash, near-dup, short titles, empty input |
| `backend/tests/test_glm5_client.py` | `_extract_json_object()` (8 tests) — plain JSON, markdown blocks, no JSON, non-dict |
| `backend/tests/test_search_escaping.py` | ILIKE escape logic (6 tests) — `%`, `_`, `\`, combined, normal |

---

## 14. GLM5 Model Name Fix (Critical Bug Fix)

**Problem:** Model name `glm5` rejected by API (HTTP 400). Correct name is `glm-5`.

**Files changed:**

| File | Change |
|------|--------|
| `.env` | `GLM5_MODEL_NAME=glm5` → `GLM5_MODEL_NAME=glm-5` |
| `docker-compose.yml` | Default value `glm5` → `glm-5` (2 places: backend + worker) |
| `backend/app/core/config.py` | `default="glm5"` → `default="glm-5"` |

---

## 15. Infrastructure: HTTPS Support

**File:** `infra/nginx/default.conf`
- Kept HTTP server block on port 80 (standalone compatible)
- Added commented-out HTTP→HTTPS redirect
- Added HTTPS server block on port 443 with SSL, HSTS header, TLSv1.2/1.3
- Fixed `listen 443 ssl http2` → `listen 443 ssl; http2 on;` (Nginx 1.27 deprecation)

**File:** `docker-compose.yml`
- Nginx: added port `${APP_SSL_PORT:-18443}:443`
- Nginx: added volume `./infra/nginx/ssl:/etc/nginx/ssl:ro`

**New files:**
- `infra/nginx/setup-ssl.sh` — Generates self-signed certs for dev (executable)
- `infra/nginx/ssl/.gitkeep`
- `infra/nginx/ssl/.gitignore` — Excludes `*.pem`

---

## 16. Security: Strong Credentials

**File:** `.env`
- `ADMIN_REFRESH_TOKEN`: `change_me` → `ocJpdHhu4sa8yWsOgEecpVi0hpmwdIRSa2KoKMJIKdk` (generated via `secrets.token_urlsafe(32)`)

Note: DB password change was reverted on server because PostgreSQL persistent volume retains the original password. To change, run `ALTER USER` in PostgreSQL first.

---

## Complete Changed Files List

```
# Frontend
frontend/components/dashboard.tsx        — Full rewrite + dark mode + category interaction
frontend/components/skeleton-card.tsx     — Grid layout + dark mode
frontend/components/theme-toggle.tsx      — NEW: dark mode toggle
frontend/components/ui/card.tsx           — Dark mode variants
frontend/components/ui/button.tsx         — Dark mode variants
frontend/components/ui/badge.tsx          — Dark mode variants
frontend/app/layout.tsx                   — Viewport, OG tags, theme script
frontend/app/globals.css                  — Animations, dark mode, scrollbar
frontend/lib/types.ts                     — category_counts, category_summaries
frontend/tailwind.config.ts              — darkMode: "class"
frontend/public/favicon.svg              — NEW: teal DNA helix icon

# Backend
backend/app/main.py                      — slowapi rate limiting
backend/app/api/routes.py                — Rate limits, timing-safe auth, Request param
backend/app/core/config.py               — GLM5 model name + timeout defaults
backend/app/models/news.py               — category_summaries column
backend/app/schemas/pipeline.py          — category_summaries field, max_length
backend/app/schemas/responses.py         — category_counts, category_summaries in responses
backend/app/services/glm5_client.py      — Prompt: require category_summaries
backend/app/services/summary.py          — Pass-through + fallback category summaries
backend/app/services/news_repository.py  — ILIKE escape, search scope, real counts, category_summaries storage
backend/app/services/database_init.py    — Alembic recommendation comment
backend/pyproject.toml                   — alembic, slowapi dependencies
backend/tests/                           — NEW: 4 test files, 35 tests
backend/alembic.ini                      — NEW: Alembic config
backend/alembic/                         — NEW: env.py, script.py.mako, versions/

# Infrastructure
docker-compose.yml                       — HTTPS port, SSL volume, model name fix
infra/nginx/default.conf                 — HTTPS server block, HSTS
infra/nginx/setup-ssl.sh                 — NEW: self-signed cert generator
infra/nginx/ssl/.gitkeep                 — NEW
infra/nginx/ssl/.gitignore               — NEW
.env                                     — Model name, timeout, admin token

# Documentation
claude_memory/CHANGELOG-2026-04-12.md    — This file
claude_review/REVIEW-2026-04-12.md       — Remaining medium-priority issues
```
