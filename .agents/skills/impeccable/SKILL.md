---
name: impeccable
description: Use when the user wants to design, redesign, shape, critique, audit, polish, clarify, distill, harden, optimize, adapt, animate, colorize, extract, or otherwise improve a frontend interface. Covers websites, landing pages, dashboards, product UI, app shells, components, forms, settings, onboarding, and empty states. Handles UX review, visual hierarchy, information architecture, cognitive load, accessibility, performance, responsive behavior, theming, anti-patterns, typography, fonts, spacing, layout, alignment, color, motion, micro-interactions, UX copy, error states, edge cases, i18n, and reusable design systems or tokens. Also use for bland designs that need to become bolder or more delightful, loud designs that should become quieter, live browser iteration on UI elements, or ambitious visual effects that should feel technically extraordinary. Not for backend-only or non-UI tasks.
---

# Impeccable Frontend Design

Designs and iterates production-grade frontend interfaces. Real working code, committed design choices, exceptional craft.

## Setup (non-optional)

Before any design work or file edits, pass these gates. Skipping them produces generic output that ignores the project.

| Gate | Required check | If fail |
|---|---|---|
| Context | The PRODUCT.md / DESIGN.md loader result is known. | Run the loader before continuing. |
| Product | PRODUCT.md exists and is not empty or placeholder. | Create or update PRODUCT.md. |
| Craft | A user-confirmed shape brief exists for this task. | Define the shape and wait for confirmation. |
| Image | Required visual probes / mocks are generated or skipped with a reason. | Resolve image generation before code. |
| Mutation | All active gates above pass. | Do not edit project files yet. |

## Core Principles

1. **Craft over Convenience**: Never settle for defaults.
2. **Visual Hierarchy**: Every element has a purpose and a weight.
3. **Motion with Meaning**: Animations should guide the user, not just decorate.
4. **Resilient Layouts**: Ensure responsiveness and edge-case handling.
