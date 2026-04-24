---
name: ui-system
description: Use this skill when designing or modifying the frontend UI, layout, visual hierarchy, component structure, or interaction patterns for the news dashboard. Do not use it for backend ingestion, classification logic, or deployment-only work.
---

# UI System Skill

## Purpose

Apply a consistent UI system for this repository's news intelligence dashboard.

This project is not a marketing website. It is a practical, information-dense product UI for daily biomedicine and cell therapy news.

## Primary goals

- Make daily summary highly visible.
- Make scanning many news cards easy.
- Keep the interface calm, compact, and trustworthy.
- Preserve responsive behavior across desktop, tablet, and mobile.

## Visual style

Target:
- clean dashboard
- light background
- restrained accent colors
- subtle borders and shadows
- small number of visual motifs
- readable typography
- compact spacing without feeling cramped

Avoid:
- oversized hero sections
- flashy gradients
- neon colors
- decorative illustrations that do not carry information
- animation-heavy interactions
- overuse of charts where simple labels/cards are enough

## Layout hierarchy

The homepage should generally prioritize:

1. header / app identity
2. last updated state
3. daily summary block
4. category filter controls
5. masonry news feed

Keep the daily summary above the fold on desktop when practical.

## Component guidance

Use small reusable components.

Expected UI building blocks:
- page shell
- top header
- summary card
- filter bar
- news card
- status badge/tag
- empty state
- loading skeleton
- error state

For cards:
- prioritize title readability
- place source and time in a compact metadata row
- use category tags consistently
- keep summaries short and scannable
- provide a clear original-link action

## Responsiveness

Default targets:
- desktop: 3 to 4 feed columns depending on width
- tablet: 2 columns
- mobile: 1 column

Do not let cards become too narrow to read comfortably.

## Accessibility

- use semantic headings
- preserve keyboard navigation
- provide visible focus states
- avoid low-contrast metadata text
- ensure link intent is obvious

## Implementation preferences

- prefer Next.js App Router patterns
- prefer server components by default
- use client components only for real interactivity
- use Tailwind and shadcn/ui primitives
- keep visual tokens simple and consistent

## Output expectations

When using this skill:
1. identify which UI areas are being changed
2. maintain consistency with the rest of the app
3. update shared components instead of duplicating styles
4. ensure loading, empty, and error states are covered
