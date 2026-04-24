---
name: masonry-feed
description: Use this skill when implementing or modifying the waterfall/masonry-style news feed, including card layout, sorting, loading behavior, pagination, and responsive column behavior. Do not use it for general page styling unrelated to the feed.
---

# Masonry Feed Skill

## Purpose

Implement a stable, readable, responsive masonry-style feed for news cards.

The feed is one of the core product surfaces. Optimize for scanability, stability, and low implementation complexity.

## Requirements

- Cards represent normalized news items.
- Feed order should default to newest first unless the product requirement says otherwise.
- Cards may have different heights because summaries vary.
- The layout must remain readable and visually aligned across breakpoints.

## Preferred implementation strategy

Start with the simplest robust solution:
- CSS columns, or
- a lightweight masonry approach

Do not start with a heavy virtualization or animation library unless performance data shows a real need.

## Card behavior

Each card should support:
- title
- source
- publish time
- category tag
- short summary
- original source link

Optional:
- image thumbnail only when reliable and visually helpful

Do not let missing images break the layout.

## Loading and state management

Provide:
- skeleton cards during initial load
- clear empty state when filters return no results
- clear retry/error state when API loading fails

Avoid layout jumps that make reading difficult.

## Filtering and sorting

The feed must work cleanly with category filters.

When filters change:
- preserve deterministic ordering
- avoid stale mixed results
- reset pagination/offset appropriately if pagination is used

## Responsiveness

Recommended targets:
- ≥1280px: 3 or 4 columns depending on card width
- 768px to 1279px: 2 columns
- <768px: 1 column

Do not chase maximum column count at the expense of readability.

## Performance guidance

- avoid unnecessary client-side re-renders
- memoize pure card components if needed
- avoid fetching all data repeatedly on small UI state changes
- prefer incremental pagination or bounded fetches over unbounded payloads

## Implementation notes

When modifying the feed:
1. check how data is fetched and sorted
2. preserve stable keys
3. verify card spacing at all breakpoints
4. verify long titles and long summaries do not break card layout
5. ensure original links remain obvious and clickable
