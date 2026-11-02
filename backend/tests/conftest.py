import json
import os
import tempfile
from pathlib import Path
from urllib.parse import parse_qs

# Isolate the SQLite cache before any app module reads settings.
os.environ["MINICLAY_DB"] = str(Path(tempfile.mkdtemp()) / "test.db")

import httpx  # noqa: E402
import pytest  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture(autouse=True)
def offline_defaults(monkeypatch):
    """No real LLM calls, no real DDGS calls, no shared provider cooldowns between tests."""
    from sources import search

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(search, "_ddgs_class", lambda: None)
    search._cooldown_until.clear()

    import dns.asyncresolver

    async def no_dns(*args, **kwargs):
        raise OSError("dns disabled in tests")

    monkeypatch.setattr(dns.asyncresolver, "resolve", no_dns)
    yield
    search._cooldown_until.clear()


GITHUB_ORG = {
    "login": "acme-ai", "name": "Acme AI", "blog": "https://acmeai.dev", "public_repos": 12,
    "html_url": "https://github.com/acme-ai", "type": "Organization", "description": "Evals for agents",
}
GITHUB_REPOS = [
    {"name": "evals", "stargazers_count": 2400, "language": "TypeScript", "description": "Eval runner", "fork": False, "archived": False, "html_url": "https://github.com/acme-ai/evals"},
    {"name": "acme-python", "stargazers_count": 310, "language": "Python", "description": "Python SDK", "fork": False, "archived": False, "html_url": "https://github.com/acme-ai/acme-python"},
    {"name": "old-fork", "stargazers_count": 9000, "language": "Go", "description": "", "fork": True, "archived": False, "html_url": ""},
]


SITES = {
    "acmeai.dev": {"/": "acme_home.html", "/pricing": "acme_pricing.html", "/trust": "acme_security.html"},
    "tinyfix.ai": {"/": "tinyfix_home.html"},
    "sweetcrumb.co": {"/": "bakery_home.html"},
}
SEARCH_RESULTS = {
    ("Acme AI", "linkedin"): "ddg_linkedin.html",
    ("Acme AI", "news"): "ddg_news.html",
    ("TinyFix", "linkedin"): "ddg_tinyfix_linkedin.html",
}


def acme_handler(request: httpx.Request) -> httpx.Response:
    host, path = request.url.host, request.url.path
    html = {"content-type": "text/html; charset=utf-8"}
    if host in SITES:
        page = SITES[host].get(path)
        if page:
            return httpx.Response(200, text=fixture(page), headers=html)
        return httpx.Response(404, text="not found", headers=html)
    if host == "api.github.com":
        if path == "/orgs/acme-ai":
            return httpx.Response(200, json=GITHUB_ORG)
        if path == "/orgs/acme-ai/repos":
            return httpx.Response(200, json=GITHUB_REPOS)
        return httpx.Response(404, json={"message": "Not Found"})
    if host == "html.duckduckgo.com":
        query = parse_qs(request.content.decode()).get("q", [""])[0]
        kind = "linkedin" if "linkedin.com" in query else "news"
        name = next((f for (company, k), f in SEARCH_RESULTS.items() if k == kind and f'"{company}"' in query), "ddg_empty.html")
        return httpx.Response(200, text=fixture(name), headers=html)
    if host == "cloudflare-dns.com":
        domain = request.url.params.get("name", "")
        return httpx.Response(200, json={"Status": 0, "Answer": [{"type": 15, "data": f"10 mx.{domain}."}]})
    return httpx.Response(404, text="")


@pytest.fixture
def acme_client():
    return httpx.AsyncClient(transport=httpx.MockTransport(acme_handler), follow_redirects=True)


@pytest.fixture
def offline_client():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("blocked", request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(refuse), follow_redirects=True)


def load_json(path: Path):
    return json.loads(path.read_text())
