import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from enrichment import enrich_company, get_cache, normalize_domain
from settings import (
    DEFAULT_SELLER_CONTEXT,
    MAX_CONCURRENCY,
    MAX_DOMAINS,
    MAX_SELLER_CONTEXT_CHARS,
    SEED_PATH,
)
from sources.http import make_client

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("miniclay.api")


def load_seed_rows() -> list:
    try:
        return json.loads(SEED_PATH.read_text())
    except (OSError, ValueError) as exc:
        log.warning("seed file not loaded: %s", exc)
        return []


@asynccontextmanager
async def lifespan(_app: FastAPI):
    rows = load_seed_rows()
    if rows:
        loaded = get_cache().seed(rows, DEFAULT_SELLER_CONTEXT)
        log.info("seeded %d cached rows (%d in seed file)", loaded, len(rows))
    yield


app = FastAPI(title="MiniClay API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EnrichRequest(BaseModel):
    domains: List[str]
    seller_context: Optional[str] = None
    refresh: bool = False


class EnrichSingleRequest(BaseModel):
    domain: str
    seller_context: Optional[str] = None
    refresh: bool = False


DOMAIN_RE = re.compile(r"^[a-z0-9][-a-z0-9.]*\.[a-z]{2,}$")


def validate_domain(domain: str) -> bool:
    return bool(domain) and " " not in domain and bool(DOMAIN_RE.match(domain))


def resolve_seller_context(raw: Optional[str]) -> str:
    context = re.sub(r"\s+", " ", (raw or "")).strip()
    if not context:
        return DEFAULT_SELLER_CONTEXT
    return context[:MAX_SELLER_CONTEXT_CHARS]


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/enrich")
async def enrich(request: EnrichRequest):
    domains: List[str] = []
    for raw in request.domains:
        domain = normalize_domain(raw)
        if domain and domain not in domains:
            domains.append(domain)

    if not domains:
        raise HTTPException(status_code=400, detail="No domains provided")
    if len(domains) > MAX_DOMAINS:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_DOMAINS} domains allowed")
    for domain in domains:
        if not validate_domain(domain):
            raise HTTPException(status_code=400, detail=f"Invalid domain format: {domain}")

    seller_context = resolve_seller_context(request.seller_context)
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async with make_client() as client:
        async def run(domain: str) -> dict:
            async with semaphore:
                return await enrich_company(domain, seller_context, client=client, refresh=request.refresh)

        results = await asyncio.gather(*(run(d) for d in domains))

    return {"results": results, "seller_context": seller_context}


@app.post("/api/enrich-single")
async def enrich_single(request: EnrichSingleRequest):
    domain = normalize_domain(request.domain)

    if not domain:
        raise HTTPException(status_code=400, detail="No domain provided")
    if not validate_domain(domain):
        raise HTTPException(status_code=400, detail=f"Invalid domain format: {domain}")

    return await enrich_company(domain, resolve_seller_context(request.seller_context), refresh=request.refresh)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
