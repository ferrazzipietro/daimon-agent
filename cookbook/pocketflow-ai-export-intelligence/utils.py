import csv
import json
import os
import re
from datetime import datetime
from urllib.parse import urlparse

import requests
import yaml
from bs4 import BeautifulSoup
from ddgs import DDGS

DEFAULT_SEEDS = {
    "countries": ["Germany", "Poland", "Romania", "Czech Republic"],
    "sectors": ["industrial automation", "packaging", "food processing"],
    "keywords": ["sales agent", "distributor", "importer", "wholesaler"],
    "exclusions": ["job", "career", "recruiting"],
}

COUNTRY_LANGUAGE = {
    "Germany": "de",
    "Poland": "pl",
    "Romania": "ro",
    "Czech Republic": "cs",
}

LANGUAGE_SYNONYMS = {
    "en": ["sales agent", "commercial agent", "distributor", "importer"],
    "de": ["Handelsvertreter", "Vertriebspartner", "Distributor", "Importeur"],
    "pl": ["przedstawiciel handlowy", "dystrybutor", "importer"],
    "ro": ["agent de vanzari", "distribuitor", "importator"],
    "cs": ["obchodni zastupce", "distributor", "dovozce"],
}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def call_llm(prompt):
    vllm_base_url = os.environ.get("VLLM_BASE_URL")
    if vllm_base_url:
        from openai import OpenAI

        model = os.environ.get("VLLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct")
        api_key = os.environ.get("VLLM_API_KEY", "token01")
        client = OpenAI(base_url=vllm_base_url, api_key=api_key)
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content
    if os.environ.get("OPENAI_API_KEY"):
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        r = client.chat.completions.create(
            model="gpt-5.4-nano",
            messages=[{"role": "user", "content": prompt}],
        )
        return r.choices[0].message.content
    if os.environ.get("ANTHROPIC_API_KEY"):
        from anthropic import Anthropic

        model = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        r = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return r.content[0].text
    if os.environ.get("GEMINI_API_KEY"):
        from google import genai
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        r = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return r.text
    raise ValueError("Set VLLM_BASE_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY")


def search_web(query, max_results=5):
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(r)
    return results


def fetch_page_text(url, timeout=10):
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible)"},
        )
    except requests.RequestException:
        return ""

    if not resp.ok or not resp.text:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:20000]


def extract_emails(text):
    return sorted(set(EMAIL_RE.findall(text or "")))


def extract_phones(text):
    return sorted(set(PHONE_RE.findall(text or "")))


def normalize_domain(url):
    if not url:
        return ""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain


def build_queries(seeds):
    countries = seeds["countries"]
    sectors = seeds["sectors"]
    queries = []
    for country in countries:
        lang = COUNTRY_LANGUAGE.get(country, "en")
        synonyms = LANGUAGE_SYNONYMS.get(lang, LANGUAGE_SYNONYMS["en"])
        for sector in sectors:
            for term in synonyms:
                q = f"{term} {sector} {country}"
                queries.append({"query": q, "country": country, "language": lang})
    return queries


def keyword_signals(text, language):
    terms = LANGUAGE_SYNONYMS.get(language, []) + LANGUAGE_SYNONYMS["en"]
    hits = [t for t in terms if t.lower() in (text or "").lower()]
    return {"keyword_hits": hits, "keyword_count": len(hits)}


def safe_yaml_list(text, key):
    if "```yaml" in text:
        yaml_str = text.split("```yaml", 1)[1].split("```", 1)[0].strip()
    else:
        yaml_str = text.strip()
    data = yaml.safe_load(yaml_str) or {}
    return data.get(key, [])


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)


def write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def write_markdown(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def timestamp():
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
