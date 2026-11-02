from conftest import fixture

import enrichment
from schemas import ContactPick
from settings import DEFAULT_SELLER_CONTEXT
from sources import contacts, website
from sources.search import SearchHit

SEARCH = "https://www.linkedin.com/search/results/people/?keywords="


def test_extract_people_from_news_and_team_pages():
    text = (
        "Chargebee co-founder and CEO Krish Subramanian said the company would expand.\n"
        "Former Chargebee CEO Bob Smith Says hello.\n"
        "Jane Roe, CTO at Chargebee, spoke at the event.\n"
        "Our Team\nFounders\nDana Park\nFounder & CEO\nLeo Grant - Head of Engineering"
    )
    people = {c.full_name: c.role for c in contacts.extract_people(text, "Chargebee")}
    assert people == {
        "Jane Roe": "CTO",
        "Krish Subramanian": "Co-Founder & CEO",
        "Dana Park": "Founder & CEO",
        "Leo Grant": "Head of Engineering",
    }


def test_profile_urls_only_come_from_profile_results():
    hits = [
        SearchHit("Krish Subramanian - Chargebee | LinkedIn", "https://in.linkedin.com/in/krishsubramanian/"),
        SearchHit("Krish Subramanian on LinkedIn: Ten years", "https://www.linkedin.com/posts/krish-1"),
    ]
    assert contacts.profile_urls(hits) == {"krish subramanian": "https://www.linkedin.com/in/krishsubramanian"}


def test_first_name_of_placeholder_is_none():
    assert contacts.first_name_of("Krish Subramanian") == "Krish"
    assert contacts.first_name_of("Not found") is None


async def test_contact_from_search_snippets_when_linkedin_search_is_empty(acme_client):
    row = await enrichment.enrich_company("chargebee.com", DEFAULT_SELLER_CONTEXT, client=acme_client, use_cache=False)
    dm = row["decision_maker"]
    assert (dm["full_name"], dm["role"], dm["source"]) == ("Krish Subramanian", "Co-Founder & CEO", "web")
    assert dm["work_email"] == "krish@chargebee.com"
    assert dm["email_status"] == "MX Verified"
    assert dm["linkedin_url"] == SEARCH + "Krish+Subramanian+Chargebee"
    assert row["ai_outreach"] == "" or row["ai_outreach"].startswith("Hey Krish, ")


async def test_contact_from_linked_team_page(acme_client):
    home = website.parse_page(fixture("quietco_home.html"), "https://quietco.dev/", "home")
    team = await website.fetch_team_page(acme_client, "quietco.dev", home)
    assert team and team.url == "https://quietco.dev/team"
    row = await enrichment.enrich_company("quietco.dev", DEFAULT_SELLER_CONTEXT, client=acme_client, use_cache=False)
    dm = row["decision_maker"]
    assert (dm["full_name"], dm["role"], dm["work_email"]) == ("Dana Park", "Founder & CEO", "dana@quietco.dev")


def _bare_bundle(**overrides):
    page = website.PageData(url="https://chargebee.com/", kind="home", title="Chargebee", text="Subscription billing for SaaS.")
    fields = dict(domain="chargebee.com", company_name="Chargebee", homepage=page, mx_hosts=["aspmx.l.google.com"])
    fields.update(overrides)
    return enrichment.SourceBundle(**fields)


def test_llm_knowledge_contact_is_kept_when_search_finds_nobody():
    pick = ContactPick(full_name="Krish Subramanian", role="Co-Founder & CEO", linkedin_url="https://www.linkedin.com/in/made-up",
                       source="knowledge", confidence="high")
    chosen = enrichment.resolve_contact(_bare_bundle(), pick)
    assert (chosen["full_name"], chosen["origin"]) == ("Krish Subramanian", "knowledge")
    assert chosen["work_email"] == "krish@chargebee.com"
    assert chosen["email_status"] == "MX Verified"
    assert chosen["linkedin_url"] == SEARCH + "Krish+Subramanian+Chargebee"  # unverified /in/ URL is not trusted


def test_low_confidence_or_unknown_contact_stays_not_found():
    pick = ContactPick(full_name="Krish Subramanian", role="CEO", linkedin_url="", source="knowledge", confidence="medium")
    assert enrichment.resolve_contact(_bare_bundle(), pick)["full_name"] == "Not found"
    nobody = ContactPick(full_name="Not found", role="", linkedin_url="", source="none", confidence="low")
    assert enrichment.resolve_contact(_bare_bundle(), nobody)["full_name"] == "Not found"


def test_llm_contact_named_in_evidence_is_kept_with_exact_profile_url():
    hits = [
        SearchHit("Krish Subramanian - Chargebee | LinkedIn", "https://www.linkedin.com/in/krishsubramanian"),
        SearchHit("Chargebee at 10", "https://news.example.com/x", "Krish Subramanian spoke about ten years of Chargebee."),
    ]
    pick = ContactPick(full_name="Krish Subramanian", role="Co-Founder & CEO", linkedin_url="", source="evidence", confidence="high")
    chosen = enrichment.resolve_contact(_bare_bundle(people_hits=hits), pick)
    assert chosen["linkedin_url"] == "https://www.linkedin.com/in/krishsubramanian"
    assert chosen["origin"] == "linkedin"


def test_evidence_beats_model_knowledge():
    people = [contacts.Candidate("Jane Roe", "CTO", SEARCH + "Jane+Roe+Chargebee", 100)]
    pick = ContactPick(full_name="Someone Else", role="CEO", linkedin_url="", source="knowledge", confidence="high")
    assert enrichment.resolve_contact(_bare_bundle(people=people), pick)["full_name"] == "Jane Roe"


def test_greeting_matches_point_of_contact():
    bundle = _bare_bundle()
    llm = ContactPick(full_name="Not found", role="", linkedin_url="", source="none", confidence="low")
    from schemas import EnrichedCompany

    result = EnrichedCompany(
        domain="chargebee.com", company_name="Chargebee", product_and_icp="Billing.", gtm_motion="Sales-Led Enterprise",
        pricing_tier_summary="Custom / contact sales",
        tech_and_live_signals=["Product: billing", "Stack: chargebee-node", "Trust: SOC 2"],
        fit_tier="Strong Fit", fit_reason="Billing workflows need risk controls.", decision_maker=llm,
        ai_outreach="Hey Krish, saw Chargebee's focus on billing automation. We help teams catch hallucinations before "
                    "they reach users. Are you handling that in-house, or open to a quick look?",
        sources_used=["Website"],
    )
    row = enrichment.build_row(bundle, DEFAULT_SELLER_CONTEXT, result).model_dump()
    assert row["decision_maker"]["full_name"] == "Not found"
    assert row["ai_outreach"].startswith("Hey there, ")
    assert "Krish" not in row["ai_outreach"]
