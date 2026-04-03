import os
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from enrichment import enrich_company

app = FastAPI(title="MiniClay API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class EnrichRequest(BaseModel):
    domains: list[str]


class EnrichSingleRequest(BaseModel):
    domain: str


def validate_domain(domain: str) -> bool:
    domain = domain.strip()
    if not domain or " " in domain:
        return False
    if not re.match(r"^[a-zA-Z0-9][-a-zA-Z0-9.]+\.[a-zA-Z]{2,}$", domain):
        return False
    return True


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/enrich")
async def enrich(request: EnrichRequest):
    domains = [d.strip() for d in request.domains if d.strip()]

    if not domains:
        raise HTTPException(status_code=400, detail="No domains provided")
    if len(domains) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 domains allowed")

    for domain in domains:
        if not validate_domain(domain):
            raise HTTPException(
                status_code=400, detail=f"Invalid domain format: {domain}"
            )

    results = []
    for domain in domains:
        result = await enrich_company(domain)
        results.append(result)

    return {"results": results}


@app.post("/api/enrich-single")
async def enrich_single(request: EnrichSingleRequest):
    domain = request.domain.strip()

    if not domain:
        raise HTTPException(status_code=400, detail="No domain provided")
    if not validate_domain(domain):
        raise HTTPException(
            status_code=400, detail=f"Invalid domain format: {domain}"
        )

    result = await enrich_company(domain)
    return result


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
