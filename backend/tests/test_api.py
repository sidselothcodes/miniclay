from fastapi.testclient import TestClient

from main import app
from settings import DEFAULT_DOMAINS


def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_default_domains_are_served_from_seeded_cache():
    with TestClient(app) as client:
        resp = client.post("/api/enrich", json={"domains": DEFAULT_DOMAINS})
    assert resp.status_code == 200
    rows = resp.json()["results"]
    assert [r["domain"] for r in rows] == DEFAULT_DOMAINS
    assert all(r["cached"] for r in rows)
    assert {r["decision_maker"]["full_name"] for r in rows} >= {"Tuomas Artman", "Malte Ubl", "Max Schoening"}


def test_validation():
    with TestClient(app) as client:
        too_many = [f"company{i}.com" for i in range(26)]
        assert client.post("/api/enrich", json={"domains": too_many}).status_code == 400
        assert client.post("/api/enrich", json={"domains": ["not a domain"]}).status_code == 400
        assert client.post("/api/enrich", json={"domains": []}).status_code == 400
        assert client.post("/api/enrich-single", json={"domain": "bad"}).status_code == 400


def test_domains_are_normalized_and_deduped():
    with TestClient(app) as client:
        resp = client.post("/api/enrich", json={"domains": ["https://www.Linear.app/pricing", "linear.app"]})
    assert [r["domain"] for r in resp.json()["results"]] == ["linear.app"]
