"""Regenerate the pre-loaded demo rows from a live pipeline run.

    cd backend && python build_seed.py            # default 5 domains
    python build_seed.py stripe.com ramp.com      # or any list

Writes backend/data/seed_results.json (cached by the API on startup) and
frontend/src/data/seed.json (rendered on first page load). Needs network
access; set OPENAI_API_KEY for LLM synthesis (otherwise the rules engine runs).
"""
import asyncio
import datetime as dt
import json
import sys

from enrichment import enrich_company
from settings import BASE_DIR, DEFAULT_DOMAINS, DEFAULT_SELLER_CONTEXT, SEED_PATH
from sources.http import make_client

FRONTEND_SEED = BASE_DIR.parent / "frontend" / "src" / "data" / "seed.json"


async def main(domains):
    async with make_client() as client:
        rows = await asyncio.gather(
            *(enrich_company(d, DEFAULT_SELLER_CONTEXT, client=client, refresh=True, use_cache=False) for d in domains)
        )
    today = dt.date.today().isoformat()
    good = []
    for row in rows:
        if row.get("status") != "success":
            print(f"  ✗ {row['domain']}: {row.get('error')} (skipped)")
            continue
        row.update(cached=True, snapshot_date=today)
        good.append(row)
        dm = row["decision_maker"]
        print(f"  ✓ {row['domain']:14} {', '.join(row['sources_used']) or 'no live sources':45} "
              f"{dm['full_name']} <{dm['work_email']}>"
              + (f"  fallbacks: {', '.join(row['fallbacks'])}" if row.get("fallbacks") else ""))
    if not good:
        sys.exit("No rows enriched; seed files left unchanged.")
    payload = json.dumps(good, indent=2, ensure_ascii=False) + "\n"
    SEED_PATH.write_text(payload)
    FRONTEND_SEED.write_text(payload)
    print(f"Wrote {len(good)} rows to {SEED_PATH} and {FRONTEND_SEED}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or DEFAULT_DOMAINS))
