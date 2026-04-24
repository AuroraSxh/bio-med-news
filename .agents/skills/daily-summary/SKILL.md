---
name: daily-summary
description: Use this skill when integrating or refining GLM5-based enrichment and the daily summary pipeline, including prompt design, output schema, validation, ranking of important news, and fallback behavior. Do not use it for generic UI work or deployment-only changes.
---

# Daily Summary Skill

## Purpose

Generate reliable model-assisted summaries for:
- individual news items
- the daily overview block on the homepage

The model provider is the server-side GLM5 endpoint available in the deployment environment.

## Design principles

- structured outputs first
- neutral tone
- concise analyst-style summaries
- explicit validation
- safe fallback when the model output is malformed

## Two-stage summarization

### Stage 1: per-item enrichment
For each news item, prefer fields like:
- one_line_summary
- category
- entities
- importance_score
- relevance_to_cell_therapy

Keep summaries compact and factual.

### Stage 2: daily rollup
Build the homepage summary from the curated set of relevant daily items.

Prefer output fields like:
- daily_summary
- top_events
- trend_signal
- category_counts

## Ranking and selection

Do not feed every low-signal news item into the daily rollup equally.

Prefer selecting items based on:
- relevance to biomedicine / cell therapy
- event importance
- originality of the event
- category balance
- recency within the target day

## Output contract

At the service boundary, require structured JSON.

Validate:
- required keys exist
- values have expected types
- category labels are allowed
- arrays have bounded lengths
- summaries are not empty placeholders

## Failure handling

On malformed model output:
1. retry once with stricter formatting instruction
2. if still invalid, log the failure clearly
3. fall back to a deterministic safe path or explicit null state

Never persist unvalidated free-form output as trusted structured data.

## Tone rules

Use:
- concise
- factual
- calm
- non-promotional

Avoid:
- hype language
- investor-relations marketing tone
- unsupported causal claims
- overly long narrative summaries

## Output expectations

When using this skill:
1. define the exact schema first
2. validate model output before DB write
3. make the daily summary reproducible from stored item-level enrichments
4. keep prompt wording aligned with product tone
