import enrichment
import knowledge
from outreach import find_violations, has_dash, word_count
from schemas import ContactPick, EnrichedCompany
from sources import contacts, website
from sources.search import SearchHit

VC_SELLER = "We build a digital workspace for VCs to track deals, founders and portfolio updates in one place."
SIGNAL_PREFIXES = ["Focus", "Portfolio", ("Scale", "Stack")]


def _fake_llm(domain, company, product, gtm, pricing, outreach, pick=None, signals=None):
    return EnrichedCompany(
        domain=domain, company_name=company, product_and_icp=product, gtm_motion=gtm, pricing_tier_summary=pricing,
        tech_and_live_signals=signals or ["Product: AI workspace", "Stack: API", "Trust: SOC 2"],
        fit_tier="Moderate Fit", fit_reason="Runs a deal workflow your workspace could replace.",
        decision_maker=pick or ContactPick(full_name="Not found", role="", linkedin_url="", source="none", confidence="low"),
        ai_outreach=outreach, sources_used=["Website"],
    )


def test_site_builder_branding_is_stripped_from_pages():
    page = website.parse_page(open("tests/fixtures/inuka_home.html").read(), "https://inuka.vc/", "home")
    assert page.host_platform == "Notion"
    assert (page.title, page.site_name, page.meta_description) == ("Inuka Capital", "", "")
    assert "Built with Notion" not in page.text
    own = website.parse_page(open("tests/fixtures/inuka_home.html").read(), "https://www.notion.so/", "home")
    assert own.site_name == "Notion" and own.host_platform == ""
    assert website.is_hosting_brand("Notion", "inuka.vc") and not website.is_hosting_brand("Notion", "notion.so")


async def test_notion_hosted_vc_is_not_called_notion(acme_client):
    row = await enrichment.enrich_company("inuka.vc", VC_SELLER, client=acme_client, use_cache=False)
    assert row["company_name"] == "Inuka Capital"
    assert "notion" not in row["product_and_icp"].lower()
    assert row["gtm_motion"] == "Early-Stage VC"
    assert row["pricing_tier_summary"] == "Pre-Seed to Seed"


async def test_llm_cannot_turn_the_site_builder_into_the_company(acme_client):
    bundle = await enrichment.collect_sources(acme_client, "inuka.vc")
    fake = _fake_llm(
        "inuka.vc", "Notion", "Notion is the AI workspace where teams write, plan and organize.",
        "Freemium PLG", "Free · Plus $10/seat", "Hey Inuka Capital team, saw your fund. Open to a quick look?",
    )
    row = enrichment.build_row(bundle, VC_SELLER, fake).model_dump()
    assert row["company_name"] == "Inuka Capital"
    assert not row["product_and_icp"].lower().startswith("notion")
    assert row["gtm_motion"] == "Early-Stage VC"
    assert row["pricing_tier_summary"] == "Pre-Seed to Seed"


async def test_vc_fund_gets_vc_labels_and_fund_signals(acme_client):
    row = await enrichment.enrich_company("northstar.com", VC_SELLER, client=acme_client, use_cache=False)
    assert row["gtm_motion"] == "Early-Stage VC"
    assert row["pricing_tier_summary"] == "Pre-Seed to Seed"
    focus, portfolio, scale = row["tech_and_live_signals"]
    assert focus == "Focus: We invest at pre-seed and seed in AI-first founders across India"
    assert portfolio == "Portfolio: Our portfolio: 30 companies and counting"
    assert scale == "Scale: $120M AUM"
    assert "Foo" not in " ".join(row["tech_and_live_signals"])


async def test_llm_saas_labels_are_replaced_for_funds(acme_client):
    bundle = await enrichment.collect_sources(acme_client, "northstar.com")
    fake = _fake_llm(
        "northstar.com", "Northstar Ventures", "Early-stage fund for AI founders in India.", "Sales-Led Enterprise",
        "Custom / contact sales", "Hey Northstar Ventures team, saw the new fund. Open to a quick look?",
        signals=["Product: Data and AI platform for marketing", "Traction: 30 companies", "Scale: $120M AUM"],
    )
    row = enrichment.build_row(bundle, VC_SELLER, fake).model_dump()
    assert row["gtm_motion"] == "Early-Stage VC"
    assert row["pricing_tier_summary"] == "Pre-Seed to Seed"
    assert [s.split(":")[0] for s in row["tech_and_live_signals"]] == ["Product", "Traction", "Scale"]


def test_linkedin_junk_never_reaches_the_role():
    raw = "Partner at PeaK XV in SF (fka Sequoia India ...Rohit Agarwal"
    assert contacts.clean_role_title(raw, "Peak XV") == "Partner"
    assert contacts.clean_role_title("Co-founder and CEO") == "Co-Founder & CEO"
    assert contacts.clean_role_title("Chief Technology Officer") == "Chief Technology Officer"
    assert contacts.clean_role_title("CTO (prev. Head of Applied AI)") == "CTO"
    hits = [SearchHit(f"Arnav Sahu - {raw}", "https://www.linkedin.com/in/arnavsahu")]
    bundle = enrichment.SourceBundle(domain="peakxv.com", company_name="Peak XV", people_hits=hits,
                                     linkedin=contacts.rank_candidates(hits, "Peak XV"))
    chosen = enrichment.resolve_contact(bundle, None)
    assert (chosen["full_name"], chosen["role"]) == ("Arnav Sahu", "Partner")
    assert chosen["linkedin_url"] == "https://www.linkedin.com/in/arnavsahu"


async def test_senseai_uses_curated_specifics_and_mentions_haystack(offline_client):
    row = await enrichment.enrich_company("senseai.ai", VC_SELLER, client=offline_client, use_cache=False)
    kb = knowledge.lookup("senseai.ai")
    assert row["product_and_icp"] == kb["product_and_icp"]
    assert (row["gtm_motion"], row["pricing_tier_summary"]) == ("Early-Stage VC", "Seed & Pre-Series A (20+ AI cos)")
    assert row["tech_and_live_signals"] == kb["signals"]
    dm = row["decision_maker"]
    assert (dm["full_name"], dm["role"], dm["work_email"]) == ("Rahul Agarwalla", "Founding & Managing Partner", "rahul@senseai.ai")
    outreach = row["ai_outreach"]
    assert outreach.startswith("Hey Rahul, ") and "Haystack" in outreach
    assert "eval" not in outreach.lower()
    assert find_violations(outreach, "Rahul", VC_SELLER) == []
    assert not has_dash(outreach) and word_count(outreach) <= 45


def test_evals_only_when_the_seller_sells_evals():
    text = "Hey Rahul, saw you run deal memos on Haystack. Are you building evals for that in-house, or open to a quick look?"
    assert any("evals" in i for i in find_violations(text, "Rahul", VC_SELLER))
    assert find_violations(text, "Rahul", "We build an LLM evaluation engine for AI teams.") == []


def test_llm_eval_closer_is_rewritten_for_other_sellers():
    bundle = enrichment.SourceBundle(domain="senseai.ai", company_name="SenseAI Ventures", kb=knowledge.lookup("senseai.ai"))
    pick = ContactPick(full_name="Rahul Agarwalla", role="Managing Partner", linkedin_url="", source="knowledge", confidence="high")
    fake = _fake_llm(
        "senseai.ai", "SenseAI Ventures", "Fund.", "Early-Stage VC", "Seed", pick=pick,
        outreach="Hey Rahul, I appreciate the work on Haystack, our tools might complement each other and enhance their "
                 "workflow. Are you building evals for that in-house, or open to a quick look?",
    )
    outreach = enrichment.build_row(bundle, VC_SELLER, fake).ai_outreach
    assert outreach.startswith("Hey Rahul, ")
    for phrase in ("eval", "I appreciate the", "complement each other", "enhance their"):
        assert phrase not in outreach
