import html
import json
import re

import enrichment
from fit import LOW, TIERS
from outreach import find_violations, has_dash, word_count
from schemas import DecisionMaker, EnrichedCompany, EnrichmentRow
from settings import DEFAULT_SELLER_CONTEXT, SEED_PATH

FRONTEND = SEED_PATH.parents[2] / "frontend" / "src"
FRONTEND_SEED = FRONTEND / "data" / "seed.json"
SIGNAL_PREFIXES = [("Launch", "Product"), ("Stack", "Traction"), ("Trust", "Scale")]


def assert_adaptive_signals(signals):
    assert len(signals) == 3
    for signal, allowed in zip(signals, SIGNAL_PREFIXES):
        assert signal.split(":", 1)[0] in allowed, signal


def assert_human_outreach(text, first_name):
    assert text.startswith(f"Hey {first_name}, ")
    assert not has_dash(text), text
    assert word_count(text) <= 45, text
    assert find_violations(text, first_name) == [], text


async def test_live_path_uses_all_five_sources(acme_client):
    row = await enrichment.enrich_company("https://www.acmeai.dev/", DEFAULT_SELLER_CONTEXT, client=acme_client, use_cache=False)
    assert row["status"] == "success"
    assert row["company_name"] == "Acme AI"
    assert row["sources_used"] == ["Website", "Pricing", "GitHub", "News", "LinkedIn"]

    dm = row["decision_maker"]
    assert (dm["full_name"], dm["role"]) == ("Jane Doe", "CTO")
    assert dm["linkedin_url"] == "https://www.linkedin.com/in/janedoe"
    assert dm["work_email"] == "jane@acmeai.dev"
    assert dm["email_status"] == "MX Verified"
    assert row["email_alternates"] == ["jdoe@acmeai.dev", "jane.doe@acmeai.dev"]

    assert "$25/user/mo" in row["pricing_tier_summary"]
    assert row["gtm_motion"] == "Freemium PLG"
    launch, stack, trust = row["tech_and_live_signals"]
    assert launch.startswith("Launch: Acme AI launches Agents API")
    assert stack.startswith("Stack: github.com/acme-ai: 12 public repos · top evals (★2.4k)")
    assert "old-fork" not in stack
    assert trust == "Trust: SOC 2 Type II, ISO 27001, HIPAA"

    assert row["fit_tier"] == "Strong Fit"
    assert row["fit_reason"] and len(row["fit_reason"].split()) <= 20
    assert_human_outreach(row["ai_outreach"], "Jane")
    assert "just launched Agents API" in row["ai_outreach"]
    assert row["fallbacks"] == []
    EnrichmentRow.model_validate(row)


async def test_small_startup_resolves_to_founder_and_adapts_signals(acme_client):
    row = await enrichment.enrich_company("tinyfix.ai", DEFAULT_SELLER_CONTEXT, client=acme_client, use_cache=False)
    dm = row["decision_maker"]
    assert (dm["full_name"], dm["role"]) == ("Sam Patel", "Co-Founder & CEO")
    assert dm["work_email"] == "sam@tinyfix.ai"
    product, traction, scale = row["tech_and_live_signals"]
    assert product.startswith("Launch: Introducing the TinyFix voice agent")
    assert traction == "Traction: Y Combinator (W25) · actively hiring"
    assert scale == "Scale: Used by 120 HVAC shops"
    assert row["fit_tier"] in TIERS and row["fit_tier"] != LOW
    assert_human_outreach(row["ai_outreach"], "Sam")
    assert row["ai_outreach"].startswith("Hey Sam, saw you're launching the TinyFix voice agent.")


async def test_consumer_brand_is_low_fit_with_no_draft(acme_client):
    row = await enrichment.enrich_company("sweetcrumb.co", DEFAULT_SELLER_CONTEXT, client=acme_client, use_cache=False)
    assert row["status"] == "success"
    assert row["fit_tier"] == "Low Fit"
    assert row["fit_reason"] == "Consumer retail brand with no customer-facing LLM workflows in production."
    assert row["ai_outreach"] == ""
    assert row["decision_maker"]["full_name"] == "Not found"
    assert row["gtm_motion"] == "Consumer D2C"
    assert_adaptive_signals(row["tech_and_live_signals"])


async def test_llm_cannot_manufacture_a_fit_for_a_consumer_brand(acme_client):
    bundle = await enrichment.collect_sources(acme_client, "sweetcrumb.co")
    fake = EnrichedCompany(
        domain="sweetcrumb.co", company_name="Sweet Crumb", product_and_icp="Bakery.", gtm_motion="Consumer D2C",
        pricing_tier_summary="Pricing not public",
        tech_and_live_signals=["Product: cakes", "Traction: Portland", "Scale: nationwide shipping"],
        fit_tier="Strong Fit", fit_reason="Uses AI to personalize cake recommendations.",
        decision_maker=DecisionMaker(full_name="Pat Baker", role="CEO", linkedin_url="https://www.linkedin.com/in/pat",
                                     work_email="pat@sweetcrumb.co", email_status="MX Verified"),
        ai_outreach="Hey Pat, saw your AI cake recommendations. We catch hallucinations. Open to a look?",
        sources_used=["Website"],
    )
    row = enrichment.build_row(bundle, DEFAULT_SELLER_CONTEXT, fake).model_dump()
    assert row["fit_tier"] == "Low Fit"
    assert row["ai_outreach"] == ""


async def test_blocked_network_falls_back_to_reference_data(offline_client):
    row = await enrichment.enrich_company("linear.app", DEFAULT_SELLER_CONTEXT, client=offline_client, use_cache=False)
    assert row["status"] == "success"
    assert row["sources_used"] == []
    assert row["decision_maker"]["full_name"] == "Tuomas Artman"
    assert row["decision_maker"]["email_status"] == "Pattern Inferred"
    assert {"decision_maker", "fit"} <= set(row["fallbacks"])
    assert row["fit_tier"] == "Moderate Fit"
    assert_adaptive_signals(row["tech_and_live_signals"])
    assert_human_outreach(row["ai_outreach"], "Tuomas")


async def test_custom_seller_context_is_assessed_live_not_from_reference(offline_client):
    seller = "We build a data-quality platform that detects schema drift and broken joins in warehouse pipelines."
    row = await enrichment.enrich_company("linear.app", seller, client=offline_client, use_cache=False)
    assert "fit" not in row["fallbacks"]
    assert row["fit_tier"] in TIERS
    if row["ai_outreach"]:
        assert_human_outreach(row["ai_outreach"], "Tuomas")
        assert "schema drift" in row["ai_outreach"]


async def test_unknown_unreachable_domain_returns_error_row(offline_client):
    row = await enrichment.enrich_company("nothing-here-xyz.io", DEFAULT_SELLER_CONTEXT, client=offline_client, use_cache=False)
    assert row["status"] == "error"
    assert "could not reach" in row["error"]


async def test_llm_output_is_grounded(acme_client):
    """A hallucinated person, an 'AI' source, slop words and em-dashes never reach the table."""
    bundle = await enrichment.collect_sources(acme_client, "acmeai.dev")
    fake = EnrichedCompany(
        domain="acmeai.dev",
        company_name="Acme AI",
        product_and_icp="Eval and replay tooling for teams shipping LLM agents.",
        gtm_motion="Freemium PLG",
        pricing_tier_summary="Free · $25/user/mo · $40/seat/mo",
        tech_and_live_signals=["Trigger: Agents API launch", "Stack/GitHub: evals, acme-python", "Compliance: SOC 2 Type II"],
        fit_tier="strong",
        fit_reason="Ships LLM agents — exactly the workflow you evaluate.",
        decision_maker=DecisionMaker(full_name="Made Up Person", role="CTO", linkedin_url="https://www.linkedin.com/in/fake",
                                     work_email="made@acmeai.dev", email_status="MX Verified"),
        ai_outreach="Hi Made — I admire how the Agents API streamlines replay! It would be a game changer -- want to chat?",
        sources_used=["Website", "AI", "Pricing"],
    )
    row = enrichment.build_row(bundle, DEFAULT_SELLER_CONTEXT, fake).model_dump()
    assert row["decision_maker"]["full_name"] == "Jane Doe"
    assert row["decision_maker"]["linkedin_url"] == "https://www.linkedin.com/in/janedoe"
    assert row["sources_used"] == ["Website", "Pricing", "LinkedIn"]
    assert row["fit_tier"] == "Strong Fit"
    assert not has_dash(row["fit_reason"])
    assert row["tech_and_live_signals"] == [
        "Launch: Agents API launch", "Stack: evals, acme-python", "Trust: SOC 2 Type II",
    ]
    assert_human_outreach(row["ai_outreach"], "Jane")
    for banned in ("admire", "streamlines", "game changer", "!"):
        assert banned not in row["ai_outreach"]
    assert row["generated_by"] == "llm"


def test_seed_rows_are_valid_and_in_sync():
    backend_rows = json.loads(SEED_PATH.read_text())
    assert backend_rows == json.loads(FRONTEND_SEED.read_text())
    assert [r["domain"] for r in backend_rows] == ["stripe.com", "notion.so", "vercel.com", "linear.app", "ramp.com"]
    for row in backend_rows:
        EnrichmentRow.model_validate(row)
        dm = row["decision_maker"]
        assert dm["linkedin_url"].startswith("https://www.linkedin.com/")
        assert dm["work_email"].endswith("@" + row["domain"])
        assert any(ch.isdigit() for ch in row["pricing_tier_summary"])
        assert "AI" not in row["sources_used"]
        assert_adaptive_signals(row["tech_and_live_signals"])
        assert row["fit_tier"] in TIERS
        assert row["fit_reason"] and len(row["fit_reason"].split()) <= 20
        assert_human_outreach(row["ai_outreach"], dm["full_name"].split()[0])


def test_table_has_seven_columns_and_no_sources_column():
    source = (FRONTEND / "components" / "EnrichmentTable.tsx").read_text()
    headers = [html.unescape(h).strip() for h in re.findall(r"<th[^>]*>(.*?)</th>", source)]
    assert headers == [
        "COMPANY", "PRODUCT & ICP", "GTM & PRICING", "KEY SIGNALS", "WHY THEY FIT", "POINT OF CONTACT", "OUTREACH DRAFT",
    ]
    assert "SOURCES" not in source
    assert "source-badge" not in source
