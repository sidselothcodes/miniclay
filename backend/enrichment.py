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


def call_openai(domain: str, metadata: dict) -> dict:
    prompt = f"""You are a lead enrichment AI. Given website metadata for a company, extract structured information and write a personalized outreach line.

Website data:
- Domain: {domain}
- Page Title: {metadata['title']}
- Meta Description: {metadata['meta_description']}
- OG Title: {metadata['og_title']}
- OG Description: {metadata['og_description']}
- Page Headings: {metadata['headings']}
- Page Content Preview: {metadata['content_preview']}

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

    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    return json.loads(content)


def call_openai_knowledge(domain: str) -> dict:
    prompt = f"""You are a lead enrichment AI. Based on your knowledge, provide company information for the domain: {domain}

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

    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

    return json.loads(content)


async def enrich_company(domain: str) -> dict:
    result = {
        "domain": domain,
        "companyName": None,
        "description": None,
        "industry": None,
        "companySize": None,
        "outreachLine": None,
        "status": "error",
        "source": None,
    }

    scraped = True
    metadata = None

    try:
        html = await fetch_website(domain)
        metadata = extract_metadata(html)
    except Exception:
        scraped = False

    if scraped and metadata:
        try:
            enriched = call_openai(domain, metadata)
            result["companyName"] = enriched.get("companyName")
            result["description"] = enriched.get("description")
            result["industry"] = enriched.get("industry")
            result["companySize"] = enriched.get("companySize")
            result["outreachLine"] = enriched.get("outreachLine")
            result["status"] = "success"
            result["source"] = "website"
            return result
        except json.JSONDecodeError:
            pass
        except Exception:
            pass

    try:
        enriched = call_openai_knowledge(domain)
        result["companyName"] = enriched.get("companyName")
        result["description"] = enriched.get("description")
        result["industry"] = enriched.get("industry")
        result["companySize"] = enriched.get("companySize")
        result["outreachLine"] = enriched.get("outreachLine")
        result["status"] = "success"
        result["source"] = "ai_knowledge"
    except json.JSONDecodeError:
        result["error"] = "AI enrichment failed — could not parse response"
    except Exception:
        result["error"] = "AI enrichment failed"

    return result
