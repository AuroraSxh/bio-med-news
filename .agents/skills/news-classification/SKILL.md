---
name: news-classification
description: Use this skill when implementing or changing category logic, category taxonomy, tagging rules, or classification prompts for news items. Do not use it for raw scraping/parsing or daily-summary generation.
---

# News Classification Skill

## Purpose

Apply a fixed and controlled taxonomy to news items so the feed, filters, and daily summary remain coherent.

## Allowed categories

Only use these categories unless the product requirements and docs are explicitly updated:

- Financing
- Clinical/Regulatory Progress
- R&D
- Partnership/Licensing
- M&A/Organization
- Manufacturing/CMC
- Policy/Industry Environment
- Other

## Classification strategy

Use a hybrid strategy:

1. deterministic keyword/rule pass
2. LLM refinement only when needed
3. validation against the allowed category list before persistence

## Heuristic guidance

### Financing
Use for:
- funding rounds
- IPOs
- private placements
- debt financing
- financing-linked strategic capital announcements

### Clinical/Regulatory Progress
Use for:
- IND/CTA clearance
- trial initiation
- interim or topline clinical results
- FDA/EMA/NMPA regulatory steps
- approval, CRL, hold, designation, filing updates

### R&D
Use for:
- preclinical findings
- platform announcements
- target discovery
- enabling technology
- research milestone updates not primarily framed as regulatory or financing news

### Partnership/Licensing
Use for:
- collaborations
- co-development
- licensing deals
- option agreements
- research alliances

### M&A/Organization
Use for:
- acquisitions
- mergers
- asset purchases
- restructuring
- major executive or organization changes when those are the main event

### Manufacturing/CMC
Use for:
- process development
- CMC updates
- manufacturing scale-up
- CDMO announcements
- facility buildout and production operations

### Policy/Industry Environment
Use for:
- policy changes
- reimbursement environment
- guideline shifts
- macro regulatory environment
- sector-wide rule changes

### Other
Use only when none of the above fits after reasonable effort.

## Important constraints

- Do not invent categories ad hoc.
- Do not return multiple primary categories unless the schema explicitly supports it.
- If ambiguity is high, select the best primary category and keep confidence/notes separately if the schema supports them.

## LLM output discipline

For model-assisted classification, prefer structured output like:
- category
- confidence
- rationale_short

The persisted category must still be one of the allowed labels.

## Output expectations

When modifying classification:
1. update shared enums/constants
2. keep frontend labels and backend schema aligned
3. verify filter UI still works
4. update docs if taxonomy changes
