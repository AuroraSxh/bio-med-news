---
name: news-ingestion
description: Use this skill when adding or changing source ingestion, parsing, normalization, deduplication, scheduling, or persistence for news items. Do not use it for frontend-only changes or purely visual work.
---

# News Ingestion Skill

## Purpose

Build and maintain a reliable ingestion pipeline for daily biomedicine and cell therapy news.

The MVP should optimize for reliability and data quality, not maximal source count.

## Pipeline order

Always preserve this flow:

1. fetch source data
2. extract candidate items
3. normalize fields
4. deduplicate
5. classify
6. summarize/enrich
7. persist
8. expose through API

## Preferred source strategy

For the MVP, prefer sources that are:
- public
- stable in structure
- high signal
- relevant to biomedicine, biotech, pharma, cell therapy, or adjacent regulatory/business news

Prefer original sources when possible:
- company newsroom / press release pages
- official announcements
- selected industry media
- structured feeds or list pages

Do not optimize for scraping the entire web on day one.

## Required normalized fields

Each normalized news item should aim to include:
- title
- canonical_url
- source_name
- published_at
- content_text
- raw_summary or excerpt when available
- language
- optional image_url
- ingestion timestamp

## Deduplication

Use layered dedupe:
- canonical URL equality
- normalized title hash
- optional similarity check for likely reposts or near-duplicates

Persist enough data to make repeated runs idempotent.

## Scheduling

The worker should handle scheduled ingestion independently from the API service.

Preferred behavior:
- multiple scheduled runs per day
- safe to re-run manually
- structured logs for start, source count, item count, dedupe count, failures, and completion

## Error handling

- fail one source without crashing the entire pipeline
- log parse failures with source context
- retry transient network/model failures conservatively
- keep partial success visible in logs

## Storage and trust model

Do not treat raw fetched text as already clean.
Normalize and validate before downstream classification and summarization.

Keep source traceability:
- original URL must remain available
- source name must remain available
- publish time must be normalized consistently

## Output expectations

When using this skill:
1. describe the source and extraction approach
2. define the normalized schema being produced
3. preserve idempotency
4. make the worker safe for repeated daily runs
