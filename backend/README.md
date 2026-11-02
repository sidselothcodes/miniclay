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

Quick check with the UI's default domains:

```bash
curl -s -X POST localhost:8000/api/enrich -H 'Content-Type: application/json' \
  -d '{"domains":["vercel.com","notion.so","sarvam.ai","bolna.ai","razorpay.com"]}' | python -m json.tool
```

Results are cached for 7 days per (domain, seller context). Add `"refresh": true` to force a fresh run, and `"seller_context": "..."` to change what the outreach pitches.

## API

| Endpoint | Body | Notes |
| --- | --- | --- |
| `POST /api/enrich` | `{domains: string[], seller_context?: string, refresh?: bool}` | Up to 25 domains, run concurrently (`MAX_CONCURRENCY`, default 5) |
| `POST /api/enrich-single` | `{domain, seller_context?, refresh?}` | Used by the UI so rows fill in progressively |
| `GET /api/health` | | |

Each row matches `schemas.EnrichmentRow`: the `EnrichedCompany` fields (including `fit_tier` and `fit_reason`) plus `generated_by` (`llm` or `rules`), `sources_used`/`source_urls` (provenance), `email_alternates`, `fallbacks` (fields filled from curated reference data) and `cached`.

## How a row is built

- `sources/website.py`: homepage + up to 2 subpages (`/pricing` first), boilerplate stripped, price, compliance and GitHub-link extraction
- `sources/github.py`: org from a homepage link, then slug guesses verified against the org's `blog` field, then GitHub search. REST API first, HTML fallback when rate-limited (set `GITHUB_TOKEN` for 5,000 req/h)
- `sources/search.py`: DDGS (`ddgs` / `duckduckgo-search`), then DuckDuckGo HTML, then Bing HTML. A failing provider is skipped for 90s
- `sources/contacts.py`: LinkedIn-scoped and general leadership searches; parses `Name - Title - Company | LinkedIn` results plus leaders named in news snippets and team pages, ranked CTO > Head of AI > VP Eng > Co-Founder > Founder > CEO (former employees and non-technical "Head of AI Sales"-type roles are demoted). Emails are `first@`, `flast@` and `first.last@`, with MX checked through dnspython, then DNS-over-HTTPS
- Point of contact precedence (`enrichment.resolve_contact`): a person found in the evidence, then a well-known exec the LLM is highly confident about (only when the evidence names nobody), else "Not found". LinkedIn shows `in/<slug>` only when that exact profile URL was in the search results, otherwise a people-search link; the outreach greeting always matches the contact, without honorifics ("Hey Vivek," for "Dr. Vivek Raghavan"; "Hey <Company> team," when none). Investor titles (Managing/General/Founding Partner, Partner, Principal) count too, and `/team`, `/about-us` and `/about` are always tried
- Geo-redirects: if a US server is served a regional site (e.g. "Razorpay USA"), the homepage is refetched as an Indian visitor (`Accept-Language: en-IN`) and region suffixes are stripped from the company name
- Site builders: pages built on Notion, Webflow, Framer, WordPress, Wix, Squarespace, Substack or Carrd have the builder's branding and boilerplate stripped, and the builder's name can never become the company (`inuka.vc` is Inuka Capital, not Notion)
- Investment firms (`.vc`/`.capital`/`.ventures`/`.fund` domains, or first-person "we invest / our portfolio / AUM" language on their own pages) get a VC motion (Early-Stage VC, Multi-Stage VC, Venture Fund), their stage focus instead of pricing, and Focus / Portfolio / Scale signals about the fund itself
- Contact roles are cleaned to short titles ("Partner at PeaK XV in SF (fka ..." becomes "Partner")
- `llm.py`: OpenAI structured output (`EnrichedCompany`) plus one repair pass if the outreach breaks the rules
- `outreach.py`: draft guardrails (`Hey <First>,`, 45-word ceiling, no em-dashes/double hyphens, no dates or asides, banned phrases) and the no-LLM composer
- `fit.py`: evidence-based Strong/Moderate/Low fit; consumer brands with no AI evidence are always Low Fit for AI sellers, whatever the LLM says
- `enrichment.py`: orchestration, grounding (sources are limited to what was fetched), and a rules-based fallback when there is no API key
- `knowledge.py`: curated reference data for the default domains and the Indian demo set (SenseAI, Sarvam, Bolna, Razorpay, Zepto, Chaayos, Chargebee), used only to fill gaps; an entry's `pinned` fields (SenseAI's) always win
- `cache.py`: SQLite cache keyed by (domain, seller context), 7-day TTL

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Tests run offline. A mocked network serves fixture pages, GitHub API responses, DuckDuckGo results and DNS answers, so the full five-source path is exercised without touching the internet.

## Environment variables

| Variable | Default | |
| --- | --- | --- |
| `OPENAI_API_KEY` | | Required for LLM synthesis; without it the rules engine runs |
| `OPENAI_MODEL` | `gpt-4o-mini` | |
| `GITHUB_TOKEN` | | Optional, raises GitHub API limits |
| `MAX_CONCURRENCY` | `5` | Domains enriched in parallel per batch request |
| `CACHE_TTL_HOURS` | `168` | |
| `MINICLAY_DB` | `backend/miniclay.db` | SQLite cache path |
