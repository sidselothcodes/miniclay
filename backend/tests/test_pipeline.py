import json

import enrichment
from outreach import find_violations
from schemas import DecisionMaker, EnrichedCompany, EnrichmentRow
from settings import DEFAULT_SELLER_CONTEXT, SEED_PATH

FRONTEND_SEED = SEED_PATH.parents[2] / "frontend" / "src" / "data" / "seed.json"


async def test_live_path_uses_all_five_sources(acme_client):
    row = await enrichment.enrich_company("https://www.acmeai.dev/", DEFAULT_SELLER_CONTEXT, client=acme_client, use_cache=False)
    assert row["status"] == "success"
    assert row["company_name"] == "Acme AI"
    assert row["sources_used"] == ["Website", "Pricing", "GitHub", "News", "LinkedIn"]
    assert "AI" not in row["sources_used"]

    dm = row["decision_maker"]
    assert (dm["full_name"], dm["role"]) == ("Jane Doe", "CTO")
    assert dm["linkedin_url"] == "https://www.linkedin.com/in/janedoe"
    assert dm["work_email"] == "jane@acmeai.dev"
    assert dm["email_status"] == "MX Verified"
    assert row["email_alternates"] == ["jdoe@acmeai.dev", "jane.doe@acmeai.dev"]

    assert "$25/user/mo" in row["pricing_tier_summary"]
    assert row["gtm_motion"] == "Freemium PLG"
    trigger, stack, compliance = row["tech_and_live_signals"]
    assert trigger.startswith("Trigger: Acme AI launches Agents API")
    assert stack.startswith("Stack/GitHub: github.com/acme-ai: 12 public repos · top evals (★2.4k)")
    assert "old-fork" not in stack  # forks are excluded
    assert compliance.startswith("Compliance: SOC 2 Type II, ISO 27001, HIPAA")

    assert row["ai_outreach"].startswith("Hi Jane —")
    assert find_violations(row["ai_outreach"], "Jane") == []
    assert row["source_urls"]["Pricing"] == ["https://acmeai.dev/pricing"]
    assert row["fallbacks"] == []
    EnrichmentRow.model_validate(row)


async def test_blocked_network_falls_back_to_reference_data(offline_client):
    row = await enrichment.enrich_company("linear.app", DEFAULT_SELLER_CONTEXT, client=offline_client, use_cache=False)
    assert row["status"] == "success"
    assert row["sources_used"] == []  # nothing was fetched live, so no badges are claimed
    assert row["decision_maker"]["full_name"] == "Tuomas Artman"
    assert row["decision_maker"]["work_email"] == "tuomas@linear.app"
    assert row["decision_maker"]["email_status"] == "Pattern Inferred"
    assert "decision_maker" in row["fallbacks"]
    assert all(cell for cell in row["tech_and_live_signals"])
    assert find_violations(row["ai_outreach"], "Tuomas") == []


async def test_unknown_unreachable_domain_returns_error_row(offline_client):
    row = await enrichment.enrich_company("nothing-here-xyz.io", DEFAULT_SELLER_CONTEXT, client=offline_client, use_cache=False)
    assert row["status"] == "error"
    assert "could not reach" in row["error"]


async def test_llm_output_is_grounded(acme_client, monkeypatch):
    """A hallucinated person, an 'AI' source and slop words never reach the table."""
    bundle = await enrichment.collect_sources(acme_client, "acmeai.dev")
    fake = EnrichedCompany(
        domain="acmeai.dev",
        company_name="Acme AI",
        product_and_icp="Eval and replay tooling for teams shipping LLM agents.",
        gtm_motion="Freemium PLG",
        pricing_tier_summary="Free · $25/user/mo · $40/seat/mo",
        tech_and_live_signals=["Agents API launch (Sep 2026)", "Stack/GitHub: evals, acme-python", "Compliance: SOC 2 Type II"],
        decision_maker=DecisionMaker(full_name="Made Up Person", role="CTO", linkedin_url="https://www.linkedin.com/in/fake",
                                     work_email="made@acmeai.dev", email_status="MX Verified"),
        ai_outreach="Hi Made — I admire how the Agents API streamlines replay! It would be a game changer for evals. Want to chat?",
        sources_used=["Website", "AI", "Pricing"],
    )
    row = enrichment.build_row(bundle, DEFAULT_SELLER_CONTEXT, fake).model_dump()
    assert row["decision_maker"]["full_name"] == "Jane Doe"
    assert row["decision_maker"]["linkedin_url"] == "https://www.linkedin.com/in/janedoe"
    assert row["sources_used"] == ["Website", "Pricing", "LinkedIn"]
    assert row["ai_outreach"].startswith("Hi Jane —")
    for banned in ("admire", "streamlines", "game changer", "!"):
        assert banned not in row["ai_outreach"]
    assert row["tech_and_live_signals"][0].startswith("Trigger: ")
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
        assert set(row["sources_used"]) <= {"Website", "Pricing", "GitHub", "News", "LinkedIn"}
        assert len(row["tech_and_live_signals"]) == 3
        assert find_violations(row["ai_outreach"], dm["full_name"].split()[0]) == [], row["domain"]
