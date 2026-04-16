---
title: Kalb Contract Reviewer
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "6.12.0"
app_file: app.py
pinned: false
license: other
---

# Kalb AI Contract Reviewer

Upload a construction contract PDF and get an AI-powered analysis covering:

- Nevada-specific legal risks (NRS compliance)
- Owner-favored clauses
- Insurance gap analysis vs. Kalb coverage
- Liquidated damages review
- Downloadable PDF report

## Setup

Set the following environment variables as **Secrets** in the Space settings:

- `OPENAI_API_KEY`
- `MISTRAL_API_KEY`

Optional overrides (defaults shown):

- `FILTER_MODEL` — default `gpt-4o`
- `ANALYSIS_MODEL` — default `gpt-4o`
