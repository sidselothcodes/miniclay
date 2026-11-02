from conftest import fixture

from sources import contacts, github, search, website
from sources.search import SearchHit


# ------------------------------ website ------------------------------

def test_parse_page_strips_boilerplate_and_finds_github():
    page = website.parse_page(fixture("acme_home.html"), "https://acmeai.dev/", "home")
    assert page.site_name == "Acme AI"
    assert "Introducing the Acme Agents API" in page.text
    for boilerplate in ("window.__DATA__", "cookies", "Privacy", "GitHub features", ".hero"):
        assert boilerplate not in page.text
    assert page.github_orgs == ["acme-ai"]  # github.com/features is ignored


def test_discover_subpages_prefers_links_then_common_paths():
    home = website.parse_page(fixture("acme_home.html"), "https://acmeai.dev/", "home")
    candidates = website.discover_subpages("acmeai.dev", home)
    assert candidates[0] == ("pricing", "https://acmeai.dev/pricing")
    assert ("security", "https://acmeai.dev/trust") in candidates
    assert [k for k, _ in candidates][:2] == ["pricing", "security"]


def test_pricing_extraction_and_gtm():
    text = website.parse_page(fixture("acme_pricing.html"), "https://acmeai.dev/pricing", "pricing").text
    points = website.extract_price_points(text)
    assert "$25/user/mo" in points
    assert "$40/seat/month" in points
    summary = website.summarize_pricing(text)
    assert summary.startswith("Free tier")
    assert "Enterprise custom" in summary
    assert website.infer_gtm_motion(text) == "Freemium PLG"
    assert website.infer_gtm_motion("Pay as you go. 2.9% + 30¢ per successful card charge") == "Usage-Based"


def test_detect_compliance():
    text = website.parse_page(fixture("acme_security.html"), "https://acmeai.dev/trust", "security").text
    assert website.detect_compliance(text) == ["SOC 2 Type II", "ISO 27001", "HIPAA"]
    assert website.detect_compliance("PCI DSS Level 1 service provider and SOC 1") == ["SOC 1", "PCI DSS"]


def test_challenge_pages_are_rejected():
    assert website.looks_like_challenge("Just a moment...", "Checking your browser before accessing")
    assert not website.looks_like_challenge("Stripe | Financial Infrastructure", "Payments " * 400)


# ------------------------------ github ------------------------------

def test_github_org_matching_requires_domain_or_exact_name():
    assert github._org_matches({"blog": "https://linear.app", "name": "Linear"}, "linear.app", "Linear")
    assert github._org_matches({"blog": "https://www.notion.com", "name": "Notion", "public_repos": 20}, "notion.so", "Notion")
    # Different company that merely shares a prefix:
    assert not github._org_matches({"blog": "https://ramp.network", "name": "Ramp Network", "public_repos": 30}, "ramp.com", "Ramp")
    assert "makenotion" in github._slug_guesses("notion.so", "Notion")


def test_describe_github():
    data = {"login": "acme-ai", "public_repos": 12, "languages": ["TypeScript", "Python"],
            "top_repos": [{"name": "evals", "stars": 2400}, {"name": "acme-python", "stars": 310}]}
    assert github.describe_github(data) == (
        "github.com/acme-ai: 12 public repos · top evals (★2.4k), acme-python (★310) · TypeScript/Python"
    )


# ------------------------------ search ------------------------------

def test_parse_ddg_html_unwraps_redirects_and_skips_ads():
    hits = search.parse_ddg_html(fixture("ddg_linkedin.html"), 10)
    assert hits[0].url == "https://www.linkedin.com/in/janedoe/"
    assert all("ads.example.com" not in h.url for h in hits)


def test_parse_bing_html():
    hits = search.parse_bing_html(fixture("bing_results.html"), 10)
    assert hits[0].title == "Tuomas Artman - Linear | LinkedIn"
    assert "Co-Founder & CTO" in hits[0].snippet


def test_news_query_uses_rolling_years():
    import datetime as dt

    q = search.news_query("Linear", "linear.app", today=dt.date(2026, 11, 1))
    assert q == '"Linear" (linear.app) (launch OR API OR AI OR funding OR enterprise OR changelog) 2025..2026'


# ------------------------------ contacts ------------------------------

def test_rank_linkedin_candidates():
    hits = search.parse_ddg_html(fixture("ddg_linkedin.html"), 10)
    ranked = contacts.rank_candidates(hits, "Acme AI")
    assert ranked[0].full_name == "Jane Doe"
    assert ranked[0].role == "CTO"
    assert ranked[0].linkedin_url == "https://www.linkedin.com/in/janedoe"
    names = [c.full_name for c in ranked]
    assert "Acme AI" not in names  # company pages are not people
    # Non-technical "Head of AI Sales" and former employees rank below real technical leaders.
    assert names.index("Bob Lee") < names.index("John Smith")
    assert names.index("Bob Lee") < names.index("Priya Raman")


def test_parse_title_formats():
    cases = [
        (SearchHit("Tuomas Artman - Linear | LinkedIn", "https://es.linkedin.com/in/tuomasartman",
                   "Co-Founder & CTO at Linear."), "Linear", ("Tuomas Artman", "Co-Founder & CTO")),
        (SearchHit("Emily Glassberg Sands - Head of Data & AI at Stripe", "https://www.linkedin.com/in/egsands/", ""),
         "Stripe", ("Emily Glassberg Sands", "Head of Data & AI")),
        (SearchHit("Malte Ubl – CTO – Vercel | LinkedIn", "https://www.linkedin.com/in/malteubl", ""),
         "Vercel", ("Malte Ubl", "CTO")),
    ]
    for hit, company, (name, role) in cases:
        cand = contacts.parse_linkedin_hit(hit, company)
        assert cand is not None, hit.title
        assert (cand.full_name, cand.role) == (name, role)
        assert cand.linkedin_url.startswith("https://www.linkedin.com/in/")


def test_small_startup_roles_resolve_to_founders():
    query = contacts.linkedin_query("TinyFix")
    for role in ('"Founder"', '"Co-Founder"', '"CEO"', '"CTO"', '"Head of AI"', '"VP Engineering"'):
        assert role in query
    hits = [
        SearchHit("Lee Wong - Founding Engineer - TinyFix | LinkedIn", "https://www.linkedin.com/in/lee"),
        SearchHit("Sam Patel - Founder & CEO - TinyFix | LinkedIn", "https://www.linkedin.com/in/sam"),
        SearchHit("Kai Ito - Engineer - TinyFix", "https://www.linkedin.com/in/kai", "CEO at TinyFix."),
    ]
    ranked = contacts.rank_candidates(hits, "TinyFix")
    assert [(c.full_name, c.role) for c in ranked][:1] == [("Sam Patel", "Founder & CEO")]
    assert "Lee Wong" not in [c.full_name for c in ranked]  # "Founding Engineer" is not a founder
    # A real CTO still outranks the CEO at larger companies.
    big = contacts.rank_candidates([
        SearchHit("Pat Lee - CEO - Acme AI", "https://www.linkedin.com/in/pat"),
        SearchHit("Jane Doe - CTO - Acme AI", "https://www.linkedin.com/in/jane"),
    ], "Acme AI")
    assert big[0].full_name == "Jane Doe"


def test_detect_traction_and_scale():
    text = website.parse_page(fixture("tinyfix_home.html"), "https://tinyfix.ai/", "home").text
    assert website.detect_traction(text) == "Y Combinator (W25) · actively hiring"
    assert website.detect_scale(text) == "Used by 120 HVAC shops"
    assert website.detect_traction("We raised $3M seed led by Foo Ventures to grow.").startswith("raised $3M")
    assert website.detect_traction("Nothing to see here.") == ""


def test_parse_rejects_non_people_and_other_companies():
    assert contacts.parse_linkedin_hit(SearchHit("Linear Team - Linear", "https://www.linkedin.com/company/linearapp"), "Linear") is None
    assert contacts.parse_linkedin_hit(SearchHit("Dan Lines - Co-founder and COO at LinearB", "https://www.linkedin.com/in/dan-lines/"), "Linear") is None


def test_email_candidates_and_status():
    assert contacts.email_candidates("Tuomas Artman", "linear.app") == [
        "tuomas@linear.app", "tartman@linear.app", "tuomas.artman@linear.app"
    ]
    assert contacts.email_candidates("José Núñez", "acme.io")[0] == "jose@acme.io"
    assert contacts.email_status(["aspmx.l.google.com"]) == "MX Verified"
    assert contacts.email_status(None) == "Pattern Inferred"


async def test_mx_lookup_falls_back_to_doh(acme_client):
    assert await contacts.lookup_mx(acme_client, "acmeai.dev") == ["mx.acmeai.dev"]
