# MiniClay — AI Lead Enrichment Demo

A mini version of [Clay's](https://clay.com) core enrichment pipeline. Paste company domains and get instant AI-powered enrichment: company info, industry classification, and personalized outreach lines.

Built by [Siddarth Seloth](https://linkedin.com/in/siddarthseloth) to demonstrate understanding of Clay's product and enrichment architecture.

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

## Run Locally

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Add your OpenAI API key to .env
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Deploy

### Backend (Railway)

1. Push to GitHub
2. Go to [railway.app](https://railway.app), create new project → "Deploy from GitHub repo"
3. Set root directory to `backend/`
4. Add environment variable: `OPENAI_API_KEY=your-key-here`
5. Railway auto-detects Python and deploys
6. Copy the generated URL (e.g., `https://miniclay-backend.up.railway.app`)

### Frontend (Vercel)

1. Go to [vercel.com](https://vercel.com), import the same GitHub repo
2. Set root directory to `frontend/`
3. Add environment variable: `VITE_API_URL=https://your-railway-url.up.railway.app`
4. Deploy


