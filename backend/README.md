# MiniClay backend

FastAPI service that enriches company domains from five free sources (Website, Pricing, GitHub, News, LinkedIn) and synthesizes a structured GTM record per domain.

## Run locally

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY
uvicorn main:app --reload --port 8000
```

Quick check with the 5 default domains:

```bash
curl -s -X POST localhost:8000/api/enrich -H 'Content-Type: application/json' \
  -d '{"domains":["stripe.com","notion.so","vercel.com","linear.app","ramp.com"]}' | python -m json.tool
```

Those 5 are pre-loaded into the cache at startup, so they return instantly. Add `"refresh": true` to force a live run, and `"seller_context": "..."` to change what the outreach pitches.

## API

| Endpoint | Body | Notes |
| --- | --- | --- |
| `POST /api/enrich` | `{domains: string[], seller_context?: string, refresh?: bool}` | Up to 25 domains, run concurrently (`MAX_CONCURRENCY`, default 5) |
| `POST /api/enrich-single` | `{domain, seller_context?, refresh?}` | Used by the UI so rows fill in progressively |
| `GET /api/health` | | |

Each row matches `schemas.EnrichmentRow`: the `EnrichedCompany` fields plus `generated_by` (`llm` or `rules`), `source_urls`, `email_alternates`, `fallbacks` (fields filled from curated reference data) and `cached`.

## How a row is built

- `sources/website.py`: homepage + up to 2 subpages (`/pricing` first), boilerplate stripped, price, compliance and GitHub-link extraction
- `sources/github.py`: org from a homepage link, then slug guesses verified against the org's `blog` field, then GitHub search. REST API first, HTML fallback when rate-limited (set `GITHUB_TOKEN` for 5,000 req/h)
- `sources/search.py`: DDGS (`ddgs` / `duckduckgo-search`), then DuckDuckGo HTML, then Bing HTML. A failing provider is skipped for 90s
- `sources/contacts.py`: parses `Name - Title - Company | LinkedIn` results and ranks CTO > Head of AI > VP Eng > co-founder (former employees and non-technical "Head of AI Sales"-type roles are demoted). Emails are `first@`, `flast@` and `first.last@`, with MX checked through dnspython, then DNS-over-HTTPS
- `llm.py`: OpenAI structured output (`EnrichedCompany`) plus one repair pass if the outreach breaks the rules
- `enrichment.py`: orchestration, grounding (the LLM can only pick a decision maker the pipeline found; sources are limited to what was fetched), and a rules-based fallback when there is no API key
- `knowledge.py`: curated reference data for the default domains, used only to fill gaps
- `cache.py`: SQLite cache keyed by (domain, seller context), 7-day TTL

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests run offline. A mocked network serves fixture pages, GitHub API responses, DuckDuckGo results and DNS answers, so the full five-source path is exercised without touching the internet.

## Refresh the pre-loaded rows

```bash
python build_seed.py                 # default 5 domains
python build_seed.py stripe.com ...  # any list
```

This runs the live pipeline and rewrites both `backend/data/seed_results.json` (cached at API startup) and `frontend/src/data/seed.json` (rendered on first page load).

## Environment variables

| Variable | Default | |
| --- | --- | --- |
| `OPENAI_API_KEY` | | Required for LLM synthesis; without it the rules engine runs |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `GITHUB_TOKEN` | | Optional, raises GitHub API limits |
| `MAX_CONCURRENCY` | `5` | Domains enriched in parallel per batch request |
| `CACHE_TTL_HOURS` | `168` | |
| `MINICLAY_DB` | `backend/miniclay.db` | SQLite cache path |
