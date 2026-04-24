# Handoff to Codex — Frontend changes (2026-04-14)

This session made **frontend-only** changes to `biomed-news-app`. No backend, API, schema, ingestion, or worker code was touched. All changes are deployed to production at `http://118.178.195.6:18080/`.

Auto-ingestion was confirmed healthy before starting: worker ran 2026-04-14 00:14 CST, 20 inserted / 6 updated / 12 dupes; next scheduled runs 12:00 and 18:00 CST daily (see `backend/worker/scheduler.py` — no changes).

---

## 1. Apple design-system refactor

Goal: restyle the whole frontend to match `apple.md` (centered 980px canvas, alternating black / `#f5f5f7` sections, SF Pro, apple-blue as sole accent, translucent glass nav, pill CTAs).

### Files modified

| File | What changed |
|---|---|
| `frontend/tailwind.config.ts` | Added `theme.extend.colors.apple.*` (black/gray/text/blue/link/linkDark/darkSurface1/darkSurface3), `fontFamily.display` + `fontFamily.text` (SF Pro stacks), `boxShadow.apple`, `borderRadius.pill` (980px), `transitionTimingFunction.apple` (cubic-bezier(0.32, 0.72, 0, 1)). |
| `frontend/app/globals.css` | Body background `#f5f5f7` / `#000` (dark), SF Pro fallbacks, Apple tracking (`-0.374px` body, `-0.28px` h1/h2, `-0.224px` captions). Retained fade-in + thin-scrollbar utilities; recolored scrollbar to apple grays (`#d2d2d7` / `#424245`). Added `@media (prefers-reduced-motion: reduce)` guard collapsing transitions to `0.01ms`. |
| `frontend/app/layout.tsx` | `<body>` now has `font-text bg-apple-gray dark:bg-apple-black`; theme bootstrap script retained. |
| `frontend/components/ui/card.tsx` | Flat `bg-white` / `bg-apple-darkSurface3`, no borders, `rounded-lg`. `CardHeader` dropped border lines; tighter bottom padding. Prop API unchanged. |
| `frontend/components/ui/badge.tsx` | `rounded-full`. Variants retuned: `default` apple-blue bg, `secondary` `#ededf2` / `apple-darkSurface1`, `outline` transparent with apple-blue border+text, `destructive` `#ff3b30`. |
| `frontend/components/ui/button.tsx` | `default` apple-blue 8px-radius pill-ish (`px-[15px] py-2`). `outline` now full pill (`rounded-pill`, `px-[18px]`) with apple-blue text+border on transparent. **New** variants: `dark` (`#1d1d1f` bg) and `ghost` (transparent → `rgba(0,0,0,0.05)` / `rgba(255,255,255,0.08)` hover). Focus ring apple-blue. Existing callsites (`default` / `outline` / `secondary` / `destructive`) remain valid. |
| `frontend/components/skeleton-card.tsx` | Swapped slate greys for apple greys (`#ededf2` / `apple-darkSurface1`); borderless shell mirrors new Card. |
| `frontend/components/theme-toggle.tsx` | Rebuilt around `Button variant="ghost"`; logic untouched. |
| `frontend/components/dashboard.tsx` | Full layout rework — described below. |

### Dashboard layout (`frontend/components/dashboard.tsx`)

- **Sticky glass nav:** 48px, `bg-black/80 backdrop-blur-[20px] backdrop-saturate-150`, SF Pro Display title on left, last-updated + status pill + refresh (ghost Button) + ThemeToggle on right, all inside a centered `max-w-[980px]` column.
- **Hero / summary section:** `bg-apple-black text-white`, `py-20`. Kicker "Daily intelligence", 40/48/56px SF Pro Display headline with `leading-[1.07]`, 19px light subtitle. Date picker + model-selector dropdown (rounded-pill outline, `apple-linkDark` text) sit directly below. `handleModelChange` + `regenerating` state preserved; spinner + "Regenerating with {model}…" lives inline in the summary body when active.
- **Search + filter strip:** `bg-apple-gray dark:bg-apple-black` `py-12`. Rounded-pill search input, horizontal category chips via `Badge` — `outline` (inactive) → `default` apple-blue (active). Kept existing `.scrollbar-thin` utility.
- **News feed:** 1/2/3-col grid of `Card`, `rounded-xl` image top, 21px SF Pro Display title, 14px body captions, entity chips as mini pills, "Learn more >" source link in `apple-link` / `apple-linkDark`. `shadow-apple` applied on hover only.
- **Pagination:** pill-radius buttons (`rounded-pill px-[22px]`), default = active / outline = inactive.
- **Footer:** `bg-apple-black py-12`, centered 12px micro copy.

No teal / emerald / indigo classes remain. All interactive tint = `apple-blue` (`apple-linkDark` on dark backgrounds).

Data fetching, handlers (`handleSearchChange`, `handleCategoryChange`, `handleModelChange`), state shape, and the `/api/summary/regenerate` contract are **untouched**.

---

## 2. Events-bubble interaction in hero summary

Replaces the old permanent two-column `lg:grid-cols-[1fr_0.9fr]` layout. Now the hero summary defaults to a centered narrative + category tiles + trend signal "waterfall", and events only appear as a side bubble on demand.

### Behavior

- **Initial state (desktop + mobile):** summary stack centered at `max-w-[640px] mx-auto`. Events list is **not** rendered.
- **On desktop (≥1024px) tile click:** summary stack shifts left (`lg:-translate-x-[220px]`) via `transition-transform duration-500 ease-apple`; bubble (`w-[360px]`, `rounded-2xl`, `shadow-apple`, `bg-apple-darkSurface1`) absolutely positioned on the right fades in from `translate-x-6 scale-95 opacity-0` → `translate-x-0 scale-100 opacity-100` using the same `ease-apple` curve. The bubble's `top` is computed dynamically so its vertical centre aligns with the clicked tile's vertical centre (see §2.3).
- **On mobile (<1024px):** summary does not shift; bubble renders inline beneath the stack (`mt-6 block animate-fade-in`) only while active; `hidden` when closed — avoids reserving empty space.
- **Close paths:**
  1. Click outside both the summary stack and the bubble (document `mousedown` listener; refs guard this).
  2. Click the same active tile again (native toggle already wired).
- **Category switch while open:** bubble stays, content crossfades via `key={selectedSummaryCategory}` on the inner `<ol>`, which reuses the existing `.animate-fade-in` utility.
- **ARIA:** tiles have `aria-expanded` + `aria-controls="events-bubble"`; bubble has `id="events-bubble"`, `role="region"`, `aria-hidden`, `aria-label="${cat} events"`.

### State, refs, effects

Added inside `Dashboard()`:

```ts
const summaryStackRef = useRef<HTMLDivElement | null>(null);
const eventsBubbleRef = useRef<HTMLDivElement | null>(null);
const summaryAreaRef  = useRef<HTMLDivElement | null>(null);
const [bubbleTop, setBubbleTop] = useState<number | null>(null);
```

Two effects:

1. **Click-outside close** (`useEffect` on `selectedSummaryCategory`): adds `document.addEventListener("mousedown", …)`; closes unless event target is inside `summaryStackRef` or `eventsBubbleRef`.
2. **Vertical alignment** (`useLayoutEffect` on `selectedSummaryCategory`): queries `[data-summary-category="…"]` inside `summaryAreaRef`, measures `getBoundingClientRect()`, sets `bubbleTop = tileCenter - bubbleHeight/2`, clamped to `[0, areaHeight - bubbleHeight]`. Re-runs on `window.resize`. Applied as inline `style={{ top: bubbleTop + "px" }}` on the bubble; `lg:transition-all` smoothly animates the `top` change when switching between tiles.

### JSX structure (`dashboard.tsx` inside the hero section, where the old grid lived)

```jsx
<div className="relative" ref={summaryAreaRef}>
  <div
    ref={summaryStackRef}
    className={cn(
      "mx-auto max-w-[640px] space-y-6 transition-transform duration-500 ease-apple",
      selectedSummaryCategory ? "lg:-translate-x-[220px]" : "lg:translate-x-0",
    )}
  >
    {/* narrative <p>, category tile buttons (data-summary-category={cat}), trend signal */}
  </div>

  <div
    ref={eventsBubbleRef}
    id="events-bubble"
    role="region"
    aria-hidden={!selectedSummaryCategory}
    style={selectedSummaryCategory && bubbleTop != null ? { top: `${bubbleTop}px` } : undefined}
    className={cn(
      "rounded-2xl bg-apple-darkSurface1 p-5 shadow-apple",
      "lg:absolute lg:right-0 lg:block lg:w-[360px] lg:transition-all lg:duration-500 lg:ease-apple",
      selectedSummaryCategory
        ? "mt-6 block animate-fade-in lg:mt-0 lg:translate-x-0 lg:scale-100 lg:opacity-100 lg:pointer-events-auto"
        : "hidden lg:top-0 lg:translate-x-6 lg:scale-95 lg:opacity-0 lg:pointer-events-none",
    )}
  >
    {/* header + <ol key={selectedSummaryCategory}> of filtered top_events */}
  </div>
</div>
```

The filter expression inside the bubble is unchanged: `summary.top_events.filter((e) => e.category === selectedSummaryCategory)`.

---

## 3. Verification

```bash
cd /Users/aurorasxh/codex_test/biomed-news-app/frontend
npx tsc --noEmit   # passes clean
npm run build      # passes clean (Next 14.2, 4 static pages)
```

Manual QA on production:

- Desktop: summary centered on load; clicking a tile slides summary left, bubble appears at the tile's vertical centre. Click another tile → bubble relocates + content crossfades. Click outside or same tile → bubble retracts, summary returns to centre. Resize window → bubble re-positions.
- Mobile: no horizontal shift; bubble drops in below summary, hides completely when closed.
- Reduced-motion OS pref collapses all transitions.
- Model selector regeneration flow still functions; "Regenerating with …" appears in place.

## 4. Deployment

Production server is `118.178.195.6`, app under `/opt/biomed-news-app`, served via nginx on port `18080`.

Files that need to be synced to production for this session (`scp -o StrictHostKeyChecking=no <file> root@118.178.195.6:<dest>`):

- `frontend/tailwind.config.ts` → `/opt/biomed-news-app/frontend/`
- `frontend/app/globals.css` → `/opt/biomed-news-app/frontend/app/`
- `frontend/app/layout.tsx` → `/opt/biomed-news-app/frontend/app/`
- `frontend/components/dashboard.tsx` → `/opt/biomed-news-app/frontend/components/`
- `frontend/components/skeleton-card.tsx` → `/opt/biomed-news-app/frontend/components/`
- `frontend/components/theme-toggle.tsx` → `/opt/biomed-news-app/frontend/components/`
- `frontend/components/ui/{card,badge,button}.tsx` → `/opt/biomed-news-app/frontend/components/ui/`

Then on the server:

```bash
cd /opt/biomed-news-app
docker compose build --no-cache frontend
docker compose up -d frontend nginx
curl -sS http://127.0.0.1/api/health   # expect status ok, database ok
```

Current status: all changes deployed, `curl http://118.178.195.6:18080/` → `200`, backend health ok.

## 5. What was NOT changed (do not reintroduce)

- `backend/` — all untouched. Worker, scheduler, ingestion freshness filter (7-day), GLM5 client rate-limit + streaming, routes (`/models`, `/summary/regenerate`) all intact.
- `lib/types.ts`, `next.config.*`, `package.json` / `package-lock.json` — no new deps added. Motion is pure CSS/Tailwind.
- No new routes/pages. No data-fetching signature changes.

## 6. Open follow-ups (not implemented, user may request later)

- "Speech-bubble tail" pseudo-element pointing from the bubble to the active tile.
- ESC key as an additional close path.
- Bubble scroll position reset on category switch (currently the inner `<ol>` is remounted via `key`, so it resets to top automatically — noted here in case that behavior is ever undone).
