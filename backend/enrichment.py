from __future__ import annotations

import json
import httpx
from bs4 import BeautifulSoup
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

def get_openai_client():
    return OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

GITHUB_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "MiniClay-Enrichment/1.0",
}


def normalize_domain(domain: str) -> str:
    domain = domain.strip().lower()
    if domain.startswith("http://") or domain.startswith("https://"):
        domain = domain.split("//", 1)[1]
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def extract_metadata(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    meta_description = ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    if meta_desc_tag and meta_desc_tag.get("content"):
        meta_description = meta_desc_tag["content"].strip()

    og_title = ""
    og_title_tag = soup.find("meta", attrs={"property": "og:title"})
    if og_title_tag and og_title_tag.get("content"):
        og_title = og_title_tag["content"].strip()

    og_description = ""
    og_desc_tag = soup.find("meta", attrs={"property": "og:description"})
    if og_desc_tag and og_desc_tag.get("content"):
        og_description = og_desc_tag["content"].strip()

    headings = []
    total_len = 0
    for tag in soup.find_all(["h1", "h2"]):
        text = tag.get_text(strip=True)
        if text and total_len < 500:
            headings.append(text)
            total_len += len(text)

    content_preview = ""
    for p in soup.find_all("p"):
        text = p.get_text(strip=True)
        if text:
            content_preview += text + " "
            if len(content_preview) > 1000:
                break
    content_preview = content_preview[:1000].strip()

    return {
        "title": title,
        "meta_description": meta_description,
        "og_title": og_title,
        "og_description": og_description,
        "headings": "; ".join(headings),
        "content_preview": content_preview,
    }


def metadata_is_useful(metadata: dict) -> bool:
    total = len(metadata.get("title", "")) + len(metadata.get("meta_description", "")) + len(metadata.get("headings", ""))
    return total >= 50


async def fetch_website(domain: str) -> str:
    bare = normalize_domain(domain)
    urls = [
        f"https://www.{bare}",
        f"https://{bare}",
    ]

    for url in urls:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True, verify=False, timeout=15.0, headers=HEADERS
            ) as client_http:
                response = await client_http.get(url)
                response.raise_for_status()
                return response.text
        except Exception:
            continue

    raise Exception("Could not reach website")


async def fetch_github_info(company_name: str) -> dict | None:
    if not company_name:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0, headers=GITHUB_HEADERS) as client_http:
            response = await client_http.get(
                "https://api.github.com/search/users",
                params={"q": f"{company_name} type:org"},
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("items"):
                return None

            org = data["items"][0]
            org_login = org.get("login", "")

            org_response = await client_http.get(f"https://api.github.com/orgs/{org_login}")
            org_response.raise_for_status()
            org_data = org_response.json()

            return {
                "github_org": org_login,
                "github_bio": org_data.get("description") or org_data.get("bio") or "",
                "github_public_repos": org_data.get("public_repos", 0),
            }
    except Exception:
        return None


def parse_gpt_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
    return json.loads(content)


def call_openai(domain: str, metadata: dict, github_info: dict | None = None) -> dict:
    github_section = ""
    if github_info:
        github_section = f"""
- GitHub Org: {github_info.get('github_org', '')}
- GitHub Bio: {github_info.get('github_bio', '')}
- Public Repos: {github_info.get('github_public_repos', 0)}"""

    prompt = f"""You are a lead enrichment AI. Given website metadata for a company, extract structured information and write a personalized outreach line.

Website data:
- Domain: {domain}
- Page Title: {metadata['title']}
- Meta Description: {metadata['meta_description']}
- OG Title: {metadata['og_title']}
- OG Description: {metadata['og_description']}
- Page Headings: {metadata['headings']}
- Page Content Preview: {metadata['content_preview']}{github_section}

Extract the following and return ONLY valid JSON, no markdown, no backticks:
{{
  "companyName": "The company's name",
  "description": "What the company does in 10-15 words max",
  "industry": "Industry category (e.g., FinTech, DevTools, Healthcare, E-commerce, AI/ML, SaaS)",
  "companySize": "One of: Startup, Mid-Market, Enterprise, Unknown",
  "outreachLine": "A 1-sentence personalized cold outreach opener. Be specific to this company. Reference what they do. Keep it casual and human. Max 25 words."
}}"""

    response = get_openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=300,
    )

    return parse_gpt_json(response.choices[0].message.content)


def call_openai_knowledge(domain: str) -> dict:
    prompt = f"""You are a lead enrichment AI. Based on your training knowledge, provide company information for the domain: {domain}

Return ONLY valid JSON, no markdown, no backticks:
{{
  "companyName": "The company's name",
  "description": "What the company does in 10-15 words max",
  "industry": "Industry category (e.g., FinTech, DevTools, Healthcare, E-commerce, AI/ML, SaaS)",
  "companySize": "One of: Startup, Mid-Market, Enterprise, Unknown",
  "outreachLine": "A 1-sentence personalized cold outreach opener. Be specific to this company. Reference what they do. Keep it casual and human. Max 25 words."
}}"""

    response = get_openai_client().chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=300,
    )

    return parse_gpt_json(response.choices[0].message.content)


def apply_enriched(result: dict, enriched: dict):
    result["companyName"] = enriched.get("companyName")
    result["description"] = enriched.get("description")
    result["industry"] = enriched.get("industry")
    result["companySize"] = enriched.get("companySize")
    result["outreachLine"] = enriched.get("outreachLine")


async def enrich_company(domain: str) -> dict:
    result = {
        "domain": domain,
        "companyName": None,
        "description": None,
        "industry": None,
        "companySize": None,
        "outreachLine": None,
        "status": "error",
        "sources": [],
    }

    metadata = None
    website_ok = False
    github_info = None

    try:
        html = await fetch_website(domain)
        metadata = extract_metadata(html)
        if metadata_is_useful(metadata):
            website_ok = True
    except Exception:
        pass

    if website_ok:
        result["sources"].append("website")

    company_name_hint = None
    if metadata and metadata.get("title"):
        company_name_hint = metadata["title"].split("|")[0].split("-")[0].split("—")[0].strip()

    github_info = await fetch_github_info(company_name_hint)
    if github_info:
        result["sources"].append("github")

    if website_ok and metadata:
        try:
            enriched = call_openai(domain, metadata, github_info)
            apply_enriched(result, enriched)
            result["status"] = "success"
            return result
        except (json.JSONDecodeError, Exception):
            pass

    try:
        enriched = call_openai_knowledge(domain)
        apply_enriched(result, enriched)
        result["status"] = "success"
        if "website" not in result["sources"]:
            result["sources"].append("ai_knowledge")
        else:
            result["sources"].append("ai_knowledge")

        if not github_info:
            company_name = enriched.get("companyName")
            github_info = await fetch_github_info(company_name)
            if github_info and "github" not in result["sources"]:
                result["sources"].append("github")

    except json.JSONDecodeError:
        result["error"] = "AI enrichment failed — could not parse response"
    except Exception:
        result["error"] = "AI enrichment failed"

    return result
