# MiniClay — GTM & Outbound Lead Enrichment Engine

Paste company domains plus one line about what you sell. MiniClay returns a Clay-style table of B2B GTM intelligence for each company: what they build and who buys it, GTM motion with real pricing, key signals, whether they actually fit what you sell, the right point of contact with a work email, and a short cold email written for that person.

Built by [Siddarth Seloth](https://linkedin.com/in/siddarthseloth)

## How It Works

1. Enter your product / value prop (the outreach context) and up to 25 company domains
2. For every domain the backend collects five sources concurrently (asyncio + httpx, per-source timeouts):
   - **Website**: homepage plus up to 2 subpages (`/pricing` first, then `/security`, `/enterprise`, `/customers`, `/about`), with nav, footer and scripts stripped
   - **Pricing**: concrete price points from the pricing page
   - **GitHub**: the company's org, public repo count, top repos and languages
   - **News**: recent launches, funding and changelog items from a free DuckDuckGo search
   - **LinkedIn**: a CTO / Head of AI / VP Eng, or the Founder/CEO at small startups, found through search, plus an inferred work email checked against the domain's MX records
3. GPT-4o-mini turns that evidence into a strict Pydantic schema. Key signals adapt to the company (Launch/Product, Stack/Traction, Trust/Scale), so 5-person startups and consumer apps get useful bullets too
4. **Why They Fit** rates each company Strong / Moderate / Low against your value prop. It never invents a fit: a bakery is a Low Fit for an LLM tool, and low-fit companies get no draft
5. Outreach drafts read like a person wrote them: "Hey Emily," plus 2–3 short sentences (30–40 words), no em-dashes, no dates or feature lists recited back, no banned phrases. The point of contact and email are grounded in what the pipeline actually found

No paid enrichment APIs. If a source gets blocked (cloud IPs are often rate-limited), the row still renders. Search falls back from DDGS to DuckDuckGo HTML to Bing HTML, and well-known companies fall back to curated reference data. The default 5 domains are pre-loaded, so the table is populated on first visit.

## Tech Stack

- **Frontend:** React, TypeScript, Vite
- **Backend:** Python, FastAPI, asyncio/httpx, BeautifulSoup4, duckduckgo-search, dnspython, SQLite cache
- **AI:** OpenAI GPT-4o-mini (structured outputs)
- **Deployment:** Vercel (frontend) + Railway (backend)

Developer notes (running locally, tests, refreshing the pre-loaded rows) are in [`backend/README.md`](backend/README.md).
