# MiniClay — GTM & Outbound Lead Enrichment Engine

Paste company domains plus one line about what you sell. MiniClay returns a Clay-style table of B2B GTM intelligence for each company: what they build and who buys it, GTM motion with real pricing, live triggers, a technical decision maker with a work email, and a 3-sentence cold email written for that person.

Built by [Siddarth Seloth](https://linkedin.com/in/siddarthseloth)

## How It Works

1. Enter your product / value prop (the outreach context) and up to 25 company domains
2. For every domain the backend collects five sources concurrently (asyncio + httpx, per-source timeouts):
   - **Website**: homepage plus up to 2 subpages (`/pricing` first, then `/security`, `/enterprise`, `/customers`, `/about`), with nav, footer and scripts stripped
   - **Pricing**: concrete price points from the pricing page
   - **GitHub**: the company's org, public repo count, top repos and languages
   - **News**: recent launches, funding and changelog items from a free DuckDuckGo search
   - **LinkedIn**: a CTO / VP Eng / Head of AI found through search, plus an inferred work email checked against the domain's MX records
3. GPT-4o-mini turns that evidence into a strict Pydantic schema. The decision maker, emails and source badges are grounded in what was actually fetched, and the outreach is checked against a banned-phrase list and a 55–65 word, 3-sentence limit
4. Results show in a Clay-style table. Every SOURCES badge links to a page the pipeline really fetched

No paid enrichment APIs. If a source gets blocked (cloud IPs are often rate-limited), the row still renders. Search falls back from DDGS to DuckDuckGo HTML to Bing HTML, and well-known companies fall back to curated reference data. The default 5 domains are pre-loaded, so the table is populated on first visit.

## Tech Stack

- **Frontend:** React, TypeScript, Vite
- **Backend:** Python, FastAPI, asyncio/httpx, BeautifulSoup4, duckduckgo-search, dnspython, SQLite cache
- **AI:** OpenAI GPT-4o-mini (structured outputs)
- **Deployment:** Vercel (frontend) + Railway (backend)

Developer notes (running locally, tests, refreshing the pre-loaded rows) are in [`backend/README.md`](backend/README.md).
