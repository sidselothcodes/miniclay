# MiniClay — AI Lead Enrichment Demo

A core enrichment pipeline. Paste company domains and get instant AI-powered enrichment: company info, industry classification, and personalized outreach lines.

Built by [Siddarth Seloth](https://linkedin.com/in/siddarthseloth)

## How It Works

1. Enter company domains (e.g., stripe.com, notion.so)
2. Backend scrapes public website metadata
3. GPT-4 extracts structured company info
4. AI generates a personalized outreach line for each lead
5. Results display in a Clay-style enrichment table

## Tech Stack

- **Frontend:** React, TypeScript, Vite
- **Backend:** Python, FastAPI, httpx, BeautifulSoup4
- **AI:** OpenAI GPT-4o-mini
- **Deployment:** Vercel (frontend) + Railway (backend)

