from conftest import fixture

import enrichment
import knowledge
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


def test_medium_confidence_knowledge_is_kept_even_if_mislabelled():
    pick = ContactPick(full_name="Krish Subramanian", role="Co-Founder & CEO", linkedin_url="",
                       source="evidence", confidence="medium")
    chosen = enrichment.resolve_contact(_bare_bundle(), pick)
    assert (chosen["full_name"], chosen["origin"]) == ("Krish Subramanian", "knowledge")


def test_low_confidence_or_unknown_contact_stays_not_found():
    pick = ContactPick(full_name="Krish Subramanian", role="CEO", linkedin_url="", source="knowledge", confidence="low")
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
    assert row["ai_outreach"].startswith("Hey Chargebee team, ")
    assert "Krish" not in row["ai_outreach"]


def _llm_result(domain, company, pick, outreach):
    from schemas import EnrichedCompany

    return EnrichedCompany(
        domain=domain, company_name=company, product_and_icp="AI products.", gtm_motion="Sales-Led Enterprise",
        pricing_tier_summary="Pricing not public",
        tech_and_live_signals=["Launch: new models", "Traction: Series A", "Scale: 10+ languages"],
        fit_tier="Strong Fit", fit_reason="Ships multilingual LLMs to enterprises.", decision_maker=pick,
        ai_outreach=outreach, sources_used=["Website"],
    )


def test_honorifics_never_reach_the_greeting_or_email():
    assert contacts.first_name_of("Dr. Vivek Raghavan") == "Vivek"
    assert contacts.first_name_of("Dr Vivek Raghavan") == "Vivek"
    assert contacts.email_candidates("Dr Vivek Raghavan", "sarvam.ai")[0] == "vivek@sarvam.ai"
    bundle = _bare_bundle(domain="sarvam.ai", company_name="Sarvam AI", kb=knowledge.lookup("sarvam.ai"))
    pick = ContactPick(full_name="Dr. Vivek Raghavan", role="Co-Founder", linkedin_url="", source="knowledge", confidence="high")
    result = _llm_result("sarvam.ai", "Sarvam AI", pick,
                         "Hey Dr., noticed you ship Indic LLMs. We catch hallucinations in Hindi chat. Open to a look?")
    row = enrichment.build_row(bundle, DEFAULT_SELLER_CONTEXT, result).model_dump()
    assert row["decision_maker"]["work_email"] == "vivek@sarvam.ai"
    assert row["ai_outreach"].startswith("Hey Vivek, ")
    assert "Dr." not in row["ai_outreach"]


def test_template_outreach_is_rewritten():
    bundle = _bare_bundle(domain="bolna.ai", company_name="Bolna", kb=knowledge.lookup("bolna.ai"))
    pick = ContactPick(full_name="Prateek Sachan", role="Co-Founder & CTO", linkedin_url="", source="knowledge", confidence="high")
    result = _llm_result("bolna.ai", "Bolna", pick,
                         "Hey there, I see you ship voice agents. Let's connect to discuss how we can support your efforts.")
    outreach = enrichment.build_row(bundle, DEFAULT_SELLER_CONTEXT, result).ai_outreach
    assert outreach.startswith("Hey Prateek, ")
    for phrase in ("Hey there", "I see you ship", "Let's connect", "support your efforts"):
        assert phrase not in outreach
    assert outreach.rstrip().endswith("?")


async def test_vc_team_page_titles(acme_client):
    row = await enrichment.enrich_company("senseai.ai", DEFAULT_SELLER_CONTEXT, client=acme_client, use_cache=False)
    dm = row["decision_maker"]
    assert (dm["full_name"], dm["role"], dm["source"]) == ("Rahul Agarwalla", "Founding & Managing Partner", "web")
    assert dm["work_email"] == "rahul@senseai.ai"
    assert row["company_name"] == "SenseAI Ventures"


async def test_geo_redirect_retries_as_indian_visitor(acme_client):
    page = await website.fetch_homepage(acme_client, "geopay.com")
    assert page.title.startswith("GeoPay - Payments, banking and payroll for Indian")
    assert not page.regional
    stuck = await website.fetch_homepage(acme_client, "stuckgeo.com")
    assert stuck.regional
    assert website.strip_region_suffix("GeoPay USA", "geopay.com") == "GeoPay"
    assert website.strip_region_suffix("Air India", "airindia.com") == "Air India"
    assert enrichment.derive_company_name(stuck, None, "geopay.com") == "GeoPay"


async def test_demo_domains_never_render_not_found_when_everything_is_blocked(offline_client):
    expected = {
        "senseai.ai": "Rahul", "sarvam.ai": "Vivek", "bolna.ai": "Prateek", "razorpay.com": "Harshil",
        "zeptonow.com": "Aadit", "chaayos.com": "Nitin", "chargebee.com": "Krish",
    }
    for domain, first in expected.items():
        row = await enrichment.enrich_company(domain, DEFAULT_SELLER_CONTEXT, client=offline_client, use_cache=False)
        assert row["decision_maker"]["full_name"].split()[0] == first, domain
        assert row["decision_maker"]["work_email"].startswith(first.lower() + "@"), domain
        if row["ai_outreach"]:
            assert row["ai_outreach"].startswith(f"Hey {first}, "), domain
    razorpay = await enrichment.enrich_company("razorpay.com", DEFAULT_SELLER_CONTEXT, client=offline_client, use_cache=False)
    assert razorpay["company_name"] == "Razorpay"
    assert razorpay["fit_tier"] != "Low Fit"
