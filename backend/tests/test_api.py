from fastapi.testclient import TestClient

from cache import EnrichmentCache, cache_key
from main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_cache_round_trip_is_scoped_to_seller_context(tmp_path):
    cache = EnrichmentCache(str(tmp_path / "cache.db"))
    key = cache_key("linear.app", "We sell evals.")
    cache.set(key, "linear.app", {"domain": "linear.app", "company_name": "Linear"})
    assert cache.get(key)["company_name"] == "Linear"
    assert cache.get(cache_key("linear.app", "We sell billing software.")) is None
    assert cache.get(key, max_age_hours=0) is None


def test_validation():
    with TestClient(app) as client:
        too_many = [f"company{i}.com" for i in range(26)]
        assert client.post("/api/enrich", json={"domains": too_many}).status_code == 400
        assert client.post("/api/enrich", json={"domains": ["not a domain"]}).status_code == 400
        assert client.post("/api/enrich", json={"domains": []}).status_code == 400
        assert client.post("/api/enrich-single", json={"domain": "bad"}).status_code == 400


def test_domains_are_normalized_and_deduped(monkeypatch):
    import main

    async def fake_enrich(domain, seller_context, **_):
        return {"domain": domain, "seller_context": seller_context}

    monkeypatch.setattr(main, "enrich_company", fake_enrich)
    with TestClient(app) as client:
        resp = client.post("/api/enrich", json={"domains": ["https://www.Linear.app/pricing", "linear.app"]})
    rows = resp.json()["results"]
    assert [r["domain"] for r in rows] == ["linear.app"]
    assert rows[0]["seller_context"] == main.DEFAULT_SELLER_CONTEXT
