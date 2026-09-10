from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import httpx
from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# Paths / environment
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend"
ENV_FILE = BASE_DIR / ".env"
CACHE_DIR = BASE_DIR / ".search_cache"

load_dotenv(ENV_FILE)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# ASCII-safe JSON response
# ============================================================

class SafeJSONResponse(JSONResponse):
    """
    The HTTP JSON payload is serialized as ASCII-safe JSON (¥¥uXXXX).
    Browsers still receive normal Unicode after JSON.parse(), but this
    avoids character-set corruption in terminals/proxies.
    """
    media_type = "application/json; charset=utf-8"

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(
    title="Research Trend Explorer",
    version="0.1.0",
    default_response_class=SafeJSONResponse,
)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


# ============================================================
# Request / response models
# ============================================================

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    field: Optional[str] = None
    foundationalCount: int = 3
    trendCount: int = 5
    papersPerTrend: int = 3
    recentYears: int = 5
    languages: List[str] = ["ja", "en"]
    publicationTypes: List[str] = ["article"]


class SearchStatusResponse(BaseModel):
    status: str
    progress: str
    result: dict
    error: Optional[str] = None


search_store: dict[str, dict] = {}


# ============================================================
# OpenAI settings
# ============================================================

MODEL_NAME = os.getenv(
    "OPENAI_MODEL",
    "gpt-5-nano",
)

SEARCH_MODEL_NAME = os.getenv(
    "OPENAI_SEARCH_MODEL",
    "gpt-5.6-luna",
)

# Keep this low during testing. Raise to 5-8 later if needed.
MAX_WEB_SEARCH_CALLS = int(
    os.getenv(
        "OPENAI_MAX_WEB_SEARCH_CALLS",
        "3",
    )
)


# ============================================================
# OpenAI client
# ============================================================

def get_openai_api_key() -> Optional[str]:
    value = os.getenv(
        "OPENAI_API_KEY",
        "",
    ).strip()
    return value or None


def get_openai_client() -> OpenAI:
    api_key = get_openai_api_key()

    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. "
            "Set OPENAI_API_KEY in your .env file."
        )

    return OpenAI(
        api_key=api_key,
        timeout=180.0,
        max_retries=1,
    )


# ============================================================
# Repair incoming Japanese mojibake only
# ============================================================

MOJIBAKE_MARKERS = (
    "蜴",
    "繧",
    "縺",
    "譁",
    "螳",
    "逕",
    "邨",
    "謖",
    "譬",
    "菴",
    "蜈",
    "鬆",
)


def repair_mojibake(text: Optional[str]) -> str:
    """
    Repairs the typical UTF-8 -> CP932/Shift_JIS mojibake seen in the
    previous runs, e.g. '蜴溷ｭ仙鴨' -> '原子力'.

    Correct Japanese/English text is left unchanged in normal cases.
    """
    if not text:
        return ""

    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text

    for encoding in ("cp932", "shift_jis"):
        try:
            candidate = text.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue

        if candidate and candidate != text:
            return candidate

    return text


# ============================================================
# Field normalization
# ============================================================

FIELD_MAP = {
    "自動判定": "Auto-detect",
    "経済学・経営学": "Economics and Management",
    "社会科学": "Social Sciences",
    "工学": "Engineering",
    "情報科学": "Computer and Information Science",
    "環境科学": "Environmental Science",
    "医学・生命科学": "Medicine and Life Sciences",
    "人文科学": "Humanities",
    "その他": "Other",
}


def normalize_field(field: Optional[str]) -> str:
    field = repair_mojibake(field)

    if not field:
        return "Auto-detect"

    return FIELD_MAP.get(field, field)


# ============================================================
# Structured Output schema
# ============================================================

def build_output_schema(
    foundational_count: int,
    trend_count: int,
    papers_per_trend: int,
    current_year: int,
) -> dict:

    source_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "url": {"type": "string"},
            "sourceType": {
                "type": "string",
                "enum": [
                    "publisher",
                    "doi",
                    "crossref",
                    "pubmed",
                    "arxiv",
                    "ssrn",
                    "repec",
                    "repository",
                    "conference",
                    "other",
                ],
            },
        },
        "required": [
            "title",
            "url",
            "sourceType",
        ],
        "additionalProperties": False,
    }

    paper_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
            },
            "authors": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "year": {
                "type": "integer",
                "minimum": 1800,
                "maximum": current_year,
            },
            "venue": {
                "type": "string",
            },
            "publicationType": {
                "type": "string",
            },
            "doi": {
                "type": [
                    "string",
                    "null",
                ],
            },
            "abstract": {
                "type": "string",
            },
            "publisherUrl": {
                "type": [
                    "string",
                    "null",
                ],
            },
            "importanceReason": {
                "type": "string",
            },
            "sources": {
                "type": "array",
                "items": source_schema,
            },
        },
        "required": [
            "title",
            "authors",
            "year",
            "venue",
            "publicationType",
            "doi",
            "abstract",
            "publisherUrl",
            "importanceReason",
            "sources",
        ],
        "additionalProperties": False,
    }

    trend_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
            },
            "description": {
                "type": "string",
            },
            "whyImportantNow": {
                "type": "string",
            },
            "researchQuestions": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "keywords": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "maturity": {
                "type": "string",
                "enum": [
                    "Emerging",
                    "Growing",
                    "Established",
                ],
            },
            "papers": {
                "type": "array",
                "items": paper_schema,
            },
        },
        "required": [
            "name",
            "description",
            "whyImportantNow",
            "researchQuestions",
            "keywords",
            "maturity",
            "papers",
        ],
        "additionalProperties": False,
    }

    return {
        "type": "object",
        "properties": {
            "normalizedTopic": {
                "type": "string",
            },
            "keywords": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
            "detectedField": {
                "type": "string",
            },
            "modelSummary": {
                "type": "string",
            },
            "foundationalPapers": {
                "type": "array",
                "items": paper_schema,
            },
            "researchTrends": {
                "type": "array",
                "items": trend_schema,
            },
            "sources": {
                "type": "array",
                "items": source_schema,
            },
            "warnings": {
                "type": "array",
                "items": {
                    "type": "string",
                },
            },
        },
        "required": [
            "normalizedTopic",
            "keywords",
            "detectedField",
            "modelSummary",
            "foundationalPapers",
            "researchTrends",
            "sources",
            "warnings",
        ],
        "additionalProperties": False,
    }


# ============================================================
# Paper helpers
# ============================================================

def make_google_scholar_url(title: str) -> str:
    return (
        "https://scholar.google.com/scholar?q="
        + quote_plus(f'"{title or ""}"')
    )


def safe_ascii_key(text: str) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        "",
        (text or "").lower(),
    )


def make_citation_key(paper: dict) -> str:
    authors = paper.get("authors") or []

    first_author = next(
        (
            author.strip()
            for author in authors
            if isinstance(author, str)
            and author.strip()
        ),
        "unknown",
    )

    parts = first_author.split()
    surname = parts[-1] if parts else "unknown"
    surname = safe_ascii_key(surname) or "unknown"

    year = paper.get("year") or "nd"

    title = paper.get("title")
    if not isinstance(title, str):
        title = ""

    words = re.findall(
        r"[A-Za-z0-9]+",
        title.lower(),
    )

    stopwords = {
        "a", "an", "the", "of", "and", "or", "for",
        "to", "in", "on", "with", "from", "by", "at",
        "as", "is", "are",
    }

    keyword = next(
        (
            word
            for word in words
            if word not in stopwords
        ),
        "paper",
    )

    return f"{surname}{year}{keyword}"


def make_bibtex_fallback(paper: dict) -> str:
    authors = [
        author.strip()
        for author in (paper.get("authors") or [])
        if isinstance(author, str)
        and author.strip()
    ]

    lines = [
        f"@article{{{make_citation_key(paper)},",
        f"  title = {{{paper.get('title') or ''}}},",
        f"  author = {{{' and '.join(authors)}}},",
        f"  year = {{{paper.get('year') or ''}}},",
        f"  journal = {{{paper.get('venue') or ''}}},",
    ]

    doi = paper.get("doi")
    if doi:
        lines.append(
            f"  doi = {{{doi}}},"
        )

    lines.append("}")
    return "¥n".join(lines)


def get_bibtex_from_doi(doi: Optional[str]) -> Optional[str]:
    """
    Try DOI content negotiation first.
    This does not scrape Google Scholar and gives a more authoritative
    BibTeX record when the DOI registration agency supports it.
    """
    if not doi:
        return None

    doi = doi.strip()
    if not doi:
        return None

    try:
        response = httpx.get(
            f"https://doi.org/{doi}",
            headers={
                "Accept": "application/x-bibtex",
                "User-Agent": "ResearchTrendExplorer/0.1",
            },
            follow_redirects=True,
            timeout=12.0,
        )

        if response.status_code == 200:
            text = response.text.strip()
            if text.startswith("@"):
                return text

    except Exception:
        pass

    return None


def is_valid_paper(paper: dict) -> bool:
    if not isinstance(paper, dict):
        return False

    title = paper.get("title")
    if not isinstance(title, str) or not title.strip():
        return False

    authors = paper.get("authors")
    if not isinstance(authors, list):
        return False

    valid_authors = [
        author.strip()
        for author in authors
        if isinstance(author, str)
        and author.strip()
    ]

    if not valid_authors:
        return False

    year = paper.get("year")
    if not isinstance(year, int):
        return False

    venue = paper.get("venue")
    if not isinstance(venue, str) or not venue.strip():
        return False

    sources = paper.get("sources")
    if not isinstance(sources, list):
        return False

    valid_source = any(
        isinstance(source, dict)
        and isinstance(source.get("url"), str)
        and source["url"].startswith(
            (
                "https://",
                "http://",
            )
        )
        for source in sources
    )

    return valid_source


def enrich_paper(
    paper: dict,
    category: str,
) -> Optional[dict]:

    if not is_valid_paper(paper):
        return None

    paper = dict(paper)

    paper["authors"] = [
        author.strip()
        for author in (paper.get("authors") or [])
        if isinstance(author, str)
        and author.strip()
    ]

    paper["id"] = str(uuid.uuid4())
    paper["category"] = category

    # Existing frontend compatibility:
    # the old UI expects abstractJa even though all text is now English.
    paper["abstractJa"] = (
        paper.get("abstract")
        or
        "No publicly available abstract was verified."
    )

    paper["googleScholarUrl"] = (
        make_google_scholar_url(
            paper.get(
                "title",
                "",
            )
        )
    )

    paper["bibtex"] = (
        get_bibtex_from_doi(
            paper.get("doi")
        )
        or
        make_bibtex_fallback(
            paper
        )
    )

    doi_exists = bool(
        paper.get("doi")
    )

    publisher_exists = bool(
        paper.get("publisherUrl")
    )

    abstract_text = (
        paper.get("abstract")
        or ""
    ).strip()

    abstract_exists = bool(
        abstract_text
        and
        abstract_text
        !=
        "No publicly available abstract was verified."
    )

    paper["verificationStatus"] = "verified"

    paper["verification"] = {
        "status": "verified",
        "titleMatched": True,
        "authorsMatched": True,
        "yearMatched": True,
        "venueMatched": True,
        "doiMatched": doi_exists,
        "publisherPageFound": publisher_exists,
        "abstractFound": abstract_exists,
    }

    return paper


# ============================================================
# Sources
# ============================================================

def deduplicate_sources(sources: list) -> list:
    result = []
    seen_urls = set()

    for source in sources:
        if not isinstance(source, dict):
            continue

        url = (
            source.get("url")
            or ""
        ).strip()

        if not url or url in seen_urls:
            continue

        seen_urls.add(url)

        source_title = source.get("title") or "Source"

        # Keep the UI English-only. Do not display garbled/non-ASCII
        # search-result titles; the URL remains available.
        if (
            not isinstance(source_title, str)
            or not source_title.isascii()
        ):
            source_title = "Source"

        result.append(
            {
                "title": source_title,
                "url": url,
                "sourceType":
                    source.get("sourceType")
                    or "other",
            }
        )

    return result


def extract_web_search_sources(response) -> list:
    try:
        payload = response.model_dump()
    except Exception:
        return []

    sources = []

    for item in (
        payload.get("output")
        or []
    ):
        if not isinstance(item, dict):
            continue

        if (
            item.get("type")
            !=
            "web_search_call"
        ):
            continue

        action = (
            item.get("action")
            or {}
        )

        for source in (
            action.get("sources")
            or []
        ):
            if not isinstance(source, dict):
                continue

            url = source.get("url")

            if not url:
                continue

            sources.append(
                {
                    "title": "Web source",
                    "url": url,
                    "sourceType": "other",
                }
            )

    return deduplicate_sources(
        sources
    )


# ============================================================
# Disk cache
# ============================================================

def cache_path(search_id: str) -> Path:
    safe_id = re.sub(
        r"[^A-Za-z0-9_-]",
        "",
        search_id,
    )
    return CACHE_DIR / f"{safe_id}.json"


def save_search(
    search_id: str,
    item: dict,
) -> None:
    try:
        path = cache_path(search_id)
        temporary = path.with_suffix(".tmp")

        temporary.write_text(
            json.dumps(
                item,
                ensure_ascii=True,
                allow_nan=False,
            ),
            encoding="utf-8",
        )

        temporary.replace(path)

    except Exception as exc:
        print(
            "CACHE WRITE WARNING:",
            repr(exc),
        )


def load_search(
    search_id: str,
) -> Optional[dict]:
    path = cache_path(search_id)

    if not path.exists():
        return None

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        print(
            "CACHE READ WARNING:",
            repr(exc),
        )
        return None


# ============================================================
# OpenAI research
# ============================================================

def research_topic(
    request: SearchRequest,
) -> dict:

    client = get_openai_client()

    raw_query = repair_mojibake(
        request.query
    ).strip()

    if not raw_query:
        raise RuntimeError(
            "The research query is empty."
        )

    now = (
        datetime
        .now()
        .astimezone()
    )

    current_year = now.year

    foundational_count = max(
        1,
        min(
            request.foundationalCount,
            10,
        ),
    )

    trend_count = max(
        1,
        min(
            request.trendCount,
            10,
        ),
    )

    papers_per_trend = max(
        1,
        min(
            request.papersPerTrend,
            10,
        ),
    )

    recent_years = max(
        1,
        min(
            request.recentYears,
            20,
        ),
    )

    from_year = (
        current_year
        - recent_years
        + 1
    )

    field = normalize_field(
        request.field
    )

    schema = build_output_schema(
        foundational_count,
        trend_count,
        papers_per_trend,
        current_year,
    )

    prompt = f"""
You are a research literature discovery assistant.

USER QUERY:
{raw_query}

USER-SPECIFIED FIELD:
{field}

SETTINGS:
- Foundational papers: up to {foundational_count}
- Research trends: up to {trend_count}
- Representative papers per trend: up to {papers_per_trend}
- Recent research period: {from_year}-{current_year}

Use web search to investigate the topic.

OUTPUT LANGUAGE:
Every human-readable explanatory field in the JSON response must be English.
The user query may be Japanese. Translate and normalize it internally.

For papers, prefer records with an official English bibliographic title.
Do not translate bibliographic titles yourself.

BIBLIOGRAPHIC ACCURACY:
Only return real academic publications whose existence you verified on the web.

Never invent or guess:
- paper title
- authors
- publication year
- journal/conference/publisher
- DOI
- paper URL

Authors are mandatory.
If at least one author cannot be verified, exclude the paper.
Never return an empty authors array.

Prefer authoritative sources:
- official publisher page
- DOI page
- Crossref
- PubMed
- arXiv
- SSRN
- RePEc
- official conference site
- university/research institute repository

DOI:
If a DOI cannot be verified, use null.
Never fabricate a DOI.

ABSTRACT:
If a publicly available abstract can be verified, summarize it faithfully
and concisely in English.

If not, set abstract exactly to:
"No publicly available abstract was verified."

Do not infer an abstract from the paper title.

FOUNDATIONAL PAPERS:
Do not restrict foundational papers to {from_year}-{current_year}.
Select papers important for the formation of the field, standard theories,
standard methods, central concepts, or major later research.
Do not simply choose recent papers.

RESEARCH TRENDS:
Use mainly literature from {from_year}-{current_year}.
Identify recurring research themes rather than isolated buzzwords.
Use recent reviews, major journals/conferences, and relevant policy or
societal developments when useful.

Maturity must be one of:
- Emerging
- Growing
- Established

MODEL SUMMARY:
Write a concise 100-180 word English overview of the research topic.

SOURCES:
Each paper must include at least one real source URL used to verify its
bibliographic information.

If fewer verified papers are available than requested, return fewer.
Accuracy is more important than filling quotas.
"""

    response = client.responses.create(
        model=SEARCH_MODEL_NAME,
        input=prompt,

        tools=[
            {
                "type": "web_search"
            }
        ],

        tool_choice="auto",

        max_tool_calls=
            MAX_WEB_SEARCH_CALLS,

        include=[
            "web_search_call.action.sources"
        ],

        reasoning={
            "effort": "none"
        },

        max_output_tokens=10000,

        text={
            "format": {
                "type": "json_schema",
                "name": "research_trend_explorer",
                "strict": True,
                "schema": schema,
            },
            "verbosity": "low",
        },

        store=False,
    )

    if not response.output_text:
        raise RuntimeError(
            "The OpenAI API returned no response body."
        )

    try:
        data = json.loads(
            response.output_text
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Failed to parse OpenAI JSON output: {exc}"
        ) from exc

    # --------------------------------------------------------
    # Foundational papers
    # --------------------------------------------------------

    foundational_papers = []
    rejected_papers = 0

    for paper in (
        data.get("foundationalPapers")
        or []
    ):
        enriched = enrich_paper(
            paper,
            "foundational",
        )

        if enriched is None:
            rejected_papers += 1
            continue

        foundational_papers.append(
            enriched
        )

        if len(foundational_papers) >= foundational_count:
            break

    # --------------------------------------------------------
    # Research trends
    # --------------------------------------------------------

    research_trends = []

    for index, trend in enumerate(
        data.get("researchTrends")
        or [],
        start=1,
    ):
        if not isinstance(trend, dict):
            continue

        clean_trend = dict(trend)
        clean_trend["id"] = (
            f"trend_{index:02d}"
        )

        # Existing frontend compatibility.
        clean_trend["nameEn"] = (
            clean_trend.get("name")
            or ""
        )
        clean_trend["nameJa"] = (
            clean_trend.get("name")
            or ""
        )

        clean_papers = []

        for paper in (
            trend.get("papers")
            or []
        ):
            enriched = enrich_paper(
                paper,
                "recent",
            )

            if enriched is None:
                rejected_papers += 1
                continue

            clean_papers.append(
                enriched
            )

            if len(clean_papers) >= papers_per_trend:
                break

        clean_trend["papers"] = clean_papers
        research_trends.append(
            clean_trend
        )

        if len(research_trends) >= trend_count:
            break

    # --------------------------------------------------------
    # Sources
    # --------------------------------------------------------

    all_sources = []

    all_sources.extend(
        data.get("sources")
        or []
    )

    for paper in foundational_papers:
        all_sources.extend(
            paper.get("sources")
            or []
        )

    for trend in research_trends:
        for paper in (
            trend.get("papers")
            or []
        ):
            all_sources.extend(
                paper.get("sources")
                or []
            )

    all_sources.extend(
        extract_web_search_sources(
            response
        )
    )

    all_sources = deduplicate_sources(
        all_sources
    )

    # --------------------------------------------------------
    # Warnings
    # --------------------------------------------------------

    warnings = [
        warning
        for warning in (
            data.get("warnings")
            or []
        )
        if isinstance(warning, str)
        and warning.isascii()
    ]

    if rejected_papers:
        warnings.append(
            f"{rejected_papers} paper(s) were excluded because "
            "their bibliographic information was incomplete."
        )

    if (
        len(foundational_papers)
        <
        foundational_count
    ):
        warnings.append(
            f"Requested {foundational_count} foundational papers; "
            f"{len(foundational_papers)} verified paper(s) are shown."
        )

    if (
        len(research_trends)
        <
        trend_count
    ):
        warnings.append(
            f"Requested {trend_count} research trends; "
            f"{len(research_trends)} trend(s) are shown."
        )

    normalized_topic = (
        data.get("normalizedTopic")
        or raw_query
    )

    keywords = [
        keyword
        for keyword in (
            data.get("keywords")
            or []
        )
        if isinstance(keyword, str)
    ]

    return {
        "querySummary": {
            # English-only visible output.
            "originalQuery":
                normalized_topic,

            "normalizedTopic":
                normalized_topic,

            # Existing frontend compatibility.
            "keywordsJa":
                [],

            "keywordsEn":
                keywords,

            "detectedField":
                data.get("detectedField")
                or field,

            "searchPeriod": {
                "from": from_year,
                "to": current_year,
            },

            "executedAt":
                now.isoformat(),

            "modelSummary":
                data.get("modelSummary")
                or "",
        },

        "foundationalPapers":
            foundational_papers,

        "researchTrends":
            research_trends,

        "sources":
            all_sources,

        "warnings":
            warnings,

        "searchMetadata": {
            "status":
                "completed",

            "modelName":
                SEARCH_MODEL_NAME,

            "maxWebSearchCalls":
                MAX_WEB_SEARCH_CALLS,

            "foundationalPaperCount":
                len(
                    foundational_papers
                ),

            "trendCount":
                len(
                    research_trends
                ),

            "recentPaperCount":
                sum(
                    len(
                        trend.get("papers")
                        or []
                    )
                    for trend
                    in research_trends
                ),

            "rejectedPaperCount":
                rejected_papers,
        },
    }


# ============================================================
# UI patch injected from main.py only
# ============================================================

UI_PATCH = r"""
<style>
.rte-generated-results {
  margin-top: 18px;
}

.rte-result-count {
  margin: 0 0 16px;
  font-size: 15px;
  font-weight: 700;
  color: #53657f;
}

.rte-paper-card {
  border: 1px solid #d8e3f2;
  border-radius: 16px;
  padding: 18px;
  margin: 14px 0;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 5px 18px rgba(25, 55, 95, 0.05);
}

.rte-paper-badge {
  display: inline-block;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.03em;
  border-radius: 999px;
  padding: 5px 9px;
  background: #e8f1ff;
  color: #2366d1;
  margin-bottom: 10px;
}

.rte-paper-title {
  margin: 0 0 8px;
  font-size: 18px;
  line-height: 1.45;
  color: #14233f;
}

.rte-meta {
  margin: 3px 0;
  color: #5d6e88;
  font-size: 14px;
}

.rte-label {
  margin: 14px 0 5px;
  font-weight: 800;
  color: #21314c;
}

.rte-body {
  margin: 0;
  line-height: 1.65;
  color: #50627e;
}

.rte-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.rte-action {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
  border: 1px solid #c9d9ef;
  border-radius: 9px;
  padding: 8px 11px;
  font-size: 13px;
  font-weight: 700;
  background: white;
  color: #1e61c7;
  cursor: pointer;
  font-family: inherit;
}

.rte-trend-card {
  border: 1px solid #d8e3f2;
  border-radius: 16px;
  margin: 14px 0;
  background: rgba(255, 255, 255, 0.78);
  overflow: hidden;
}

.rte-trend-card > summary {
  cursor: pointer;
  padding: 17px 18px;
  font-weight: 800;
  color: #14233f;
  list-style: none;
}

.rte-trend-card > summary::-webkit-details-marker {
  display: none;
}

.rte-trend-content {
  padding: 0 18px 18px;
}

.rte-maturity {
  display: inline-block;
  margin-left: 8px;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  background: #eef3fa;
  color: #53657f;
  vertical-align: middle;
}

.rte-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.rte-keyword {
  font-size: 12px;
  border-radius: 999px;
  padding: 4px 8px;
  background: #f1f5fb;
  color: #53657f;
}

.rte-rq {
  margin: 6px 0 0 20px;
  color: #50627e;
  line-height: 1.55;
}

.rte-warning {
  border: 1px solid #ead7a1;
  border-radius: 10px;
  padding: 10px 12px;
  margin: 8px 0;
  background: #fffbef;
  color: #6b5a2a;
  font-size: 13px;
}

.rte-fallback {
  max-width: 1200px;
  margin: 24px auto;
  padding: 24px;
  border: 1px solid #d8e3f2;
  border-radius: 18px;
  background: white;
}

.rte-fallback h2 {
  color: #14233f;
}

.rte-loading-note {
  margin-top: 10px;
  color: #53657f;
  font-size: 13px;
}
</style>

<script>
(() => {
  "use strict";

  const nativeFetch = window.fetch.bind(window);

  let latestSearchId = null;
  let latestResult = null;
  let renderedSearchId = null;
  let activeLoadId = null;

  const staticTranslations = new Map([
    ["研究テーマから、文献の入口を整理する",
     "Navigate the Literature from a Research Topic"],

    ["基礎文献・研究潮流・代表研究を、信頼性を重視して一目で確認できます。",
     "Review foundational papers, research trends, and representative studies with a focus on reliability."],

    ["研究テーマを入力",
     "Enter a Research Topic"],

    ["日本語・英語のキーワードを入れて、関連する研究の入口を探索できます。",
     "Enter a keyword or research topic to explore relevant literature."],

    ["研究テーマ",
     "Research Topic"],

    ["研究分野",
     "Research Field"],

    ["自動判定",
     "Auto-detect"],

    ["経済学・経営学",
     "Economics and Management"],

    ["社会科学",
     "Social Sciences"],

    ["工学",
     "Engineering"],

    ["情報科学",
     "Computer and Information Science"],

    ["環境科学",
     "Environmental Science"],

    ["医学・生命科学",
     "Medicine and Life Sciences"],

    ["人文科学",
     "Humanities"],

    ["その他",
     "Other"],

    ["研究テーマを探索",
     "Explore Research Topic"],

    ["検索IDを受け取りました",
     "Search ID received"],

    ["結果の取得を開始します…",
     "Retrieving results..."],

    ["結果の取得を開始します...",
     "Retrieving results..."],

    ["検索テーマ",
     "Research Topic"],

    ["分野:",
     "Field:"],

    ["検索期間:",
     "Search period:"],

    ["モデル要約はまだありません。",
     "No research summary yet."],

    ["まだ基礎文献データはありません",
     "No foundational papers yet"],

    ["検索結果の中から、分野理解に重要な文献を整理します。",
     "Important literature for understanding the field will appear here."],

    ["まだ研究潮流データはありません",
     "No research trends yet"],

    ["現在注目されているテーマを、成熟度ごとに整理します。",
     "Current research themes will appear here."]
  ]);


  function translateString(value) {
    if (!value) {
      return value;
    }

    const trimmed = value.trim();

    if (staticTranslations.has(trimmed)) {
      return value.replace(
        trimmed,
        staticTranslations.get(trimmed)
      );
    }

    let match = trimmed.match(
      /^(¥¥d+)¥¥s*件の基礎文献候補$/
    );

    if (match) {
      return value.replace(
        trimmed,
        `${match[1]} foundational paper candidates`
      );
    }

    match = trimmed.match(
      /^(¥¥d+)¥¥s*件の研究潮流候補$/
    );

    if (match) {
      return value.replace(
        trimmed,
        `${match[1]} research trend candidates`
      );
    }

    return value;
  }


  function translateUI(root = document.body) {
    if (!root) {
      return;
    }

    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT
    );

    const nodes = [];

    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }

    for (const node of nodes) {
      const oldText = node.nodeValue || "";
      const newText = translateString(oldText);

      if (newText !== oldText) {
        node.nodeValue = newText;
      }
    }

    if (!root.querySelectorAll) {
      return;
    }

    for (const option of root.querySelectorAll("option")) {
      const oldText = option.textContent || "";
      const newText = translateString(oldText);

      if (newText !== oldText) {
        option.textContent = newText;
      }
    }
  }


  function createElement(tag, className, text) {
    const el = document.createElement(tag);

    if (className) {
      el.className = className;
    }

    if (
      text !== undefined
      &&
      text !== null
    ) {
      el.textContent = String(text);
    }

    return el;
  }


  function findLeafWithExactText(text) {
    const elements = document.querySelectorAll(
      "h1,h2,h3,h4,h5,h6,p,span,strong,div"
    );

    for (const el of elements) {
      if (
        el.children.length === 0
        &&
        (el.textContent || "").trim() === text
      ) {
        return el;
      }
    }

    return null;
  }


  function findSectionPanel(headingText, clues) {
    const heading = findLeafWithExactText(
      headingText
    );

    if (!heading) {
      return null;
    }

    let node = heading.parentElement;

    while (
      node
      &&
      node !== document.body
    ) {
      const text = node.textContent || "";

      if (
        clues.some(
          clue => text.includes(clue)
        )
        &&
        node.getBoundingClientRect().width > 300
      ) {
        return node;
      }

      node = node.parentElement;
    }

    return (
      heading.parentElement
      ||
      null
    );
  }


  function hideLegacySectionText(panel, type) {
    if (!panel) {
      return;
    }

    const elements = panel.querySelectorAll(
      "p,div,span"
    );

    for (const el of elements) {
      if (
        el.closest(".rte-generated-results")
        ||
        el.classList.contains("rte-generated-results")
      ) {
        continue;
      }

      if (el.children.length !== 0) {
        continue;
      }

      const text = (el.textContent || "").trim();

      if (type === "foundational") {
        if (
          text === "No foundational papers yet"
          ||
          text === "Important literature for understanding the field will appear here."
          ||
          /^¥¥d+¥¥s+foundational paper candidates$/.test(text)
          ||
          /^¥¥d+¥¥s*件の基礎文献候補$/.test(text)
          ||
          text === "検索結果の中から、分野理解に重要な文献を整理します。"
        ) {
          el.style.display = "none";
        }
      }

      if (type === "trends") {
        if (
          text === "No research trends yet"
          ||
          text === "Current research themes will appear here."
          ||
          /^¥¥d+¥¥s+research trend candidates$/.test(text)
          ||
          /^¥¥d+¥¥s*件の研究潮流候補$/.test(text)
          ||
          text === "現在注目されているテーマを、成熟度ごとに整理します。"
        ) {
          el.style.display = "none";
        }
      }
    }
  }


  function createActionLink(label, href) {
    if (!href) {
      return null;
    }

    const link = createElement(
      "a",
      "rte-action",
      label
    );

    link.href = href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";

    return link;
  }


  function renderPaperCard(paper, badgeText) {
    const card = createElement(
      "article",
      "rte-paper-card"
    );

    card.appendChild(
      createElement(
        "div",
        "rte-paper-badge",
        badgeText
      )
    );

    card.appendChild(
      createElement(
        "h3",
        "rte-paper-title",
        paper.title || "Untitled paper"
      )
    );

    const authors = Array.isArray(paper.authors)
      ? paper.authors.filter(Boolean).join(", ")
      : "";

    const authorYear = [
      authors,
      paper.year
    ].filter(Boolean).join(" · ");

    if (authorYear) {
      card.appendChild(
        createElement(
          "p",
          "rte-meta",
          authorYear
        )
      );
    }

    if (paper.venue) {
      card.appendChild(
        createElement(
          "p",
          "rte-meta",
          paper.venue
        )
      );
    }

    if (paper.doi) {
      card.appendChild(
        createElement(
          "p",
          "rte-meta",
          `DOI: ${paper.doi}`
        )
      );
    }

    card.appendChild(
      createElement(
        "div",
        "rte-label",
        "Abstract / Summary"
      )
    );

    card.appendChild(
      createElement(
        "p",
        "rte-body",
        paper.abstract
        ||
        paper.abstractJa
        ||
        "No publicly available abstract was verified."
      )
    );

    card.appendChild(
      createElement(
        "div",
        "rte-label",
        "Why this paper matters"
      )
    );

    card.appendChild(
      createElement(
        "p",
        "rte-body",
        paper.importanceReason
        ||
        "No explanation available."
      )
    );

    const actions = createElement(
      "div",
      "rte-actions"
    );

    const publisher = createActionLink(
      "Publisher / Paper",
      paper.publisherUrl
    );

    if (publisher) {
      actions.appendChild(publisher);
    }

    if (paper.doi) {
      actions.appendChild(
        createActionLink(
          "DOI",
          `https://doi.org/${paper.doi}`
        )
      );
    }

    const scholar = createActionLink(
      "Google Scholar",
      paper.googleScholarUrl
    );

    if (scholar) {
      actions.appendChild(scholar);
    }

    if (paper.bibtex) {
      const button = createElement(
        "button",
        "rte-action",
        "Copy BibTeX"
      );

      button.type = "button";

      button.addEventListener(
        "click",
        async () => {
          try {
            await navigator.clipboard.writeText(
              paper.bibtex
            );

            const oldText = button.textContent;
            button.textContent = "Copied";

            setTimeout(
              () => {
                button.textContent = oldText;
              },
              1200
            );
          } catch (error) {
            console.error(
              "BibTeX copy failed:",
              error
            );
          }
        }
      );

      actions.appendChild(button);
    }

    card.appendChild(actions);

    return card;
  }


  function renderFoundational(result) {
    const papers = Array.isArray(
      result.foundationalPapers
    )
      ? result.foundationalPapers
      : [];

    let panel = findSectionPanel(
      "Foundational Papers",
      [
        "foundation",
        "基礎文献"
      ]
    );

    if (!panel) {
      return false;
    }

    hideLegacySectionText(
      panel,
      "foundational"
    );

    const old = panel.querySelector(
      ".rte-generated-results[data-section='foundational']"
    );

    if (old) {
      old.remove();
    }

    const wrapper = createElement(
      "div",
      "rte-generated-results"
    );

    wrapper.dataset.section = "foundational";

    wrapper.appendChild(
      createElement(
        "div",
        "rte-result-count",
        `${papers.length} foundational paper${papers.length === 1 ? "" : "s"} found`
      )
    );

    if (!papers.length) {
      wrapper.appendChild(
        createElement(
          "p",
          "rte-body",
          "No verified foundational papers were returned."
        )
      );
    }

    for (const paper of papers) {
      wrapper.appendChild(
        renderPaperCard(
          paper,
          "Foundational Paper"
        )
      );
    }

    panel.appendChild(wrapper);

    return true;
  }


  function renderTrends(result) {
    const trends = Array.isArray(
      result.researchTrends
    )
      ? result.researchTrends
      : [];

    let panel = findSectionPanel(
      "Research Trends",
      [
        "research trend",
        "研究潮流"
      ]
    );

    if (!panel) {
      return false;
    }

    hideLegacySectionText(
      panel,
      "trends"
    );

    const old = panel.querySelector(
      ".rte-generated-results[data-section='trends']"
    );

    if (old) {
      old.remove();
    }

    const wrapper = createElement(
      "div",
      "rte-generated-results"
    );

    wrapper.dataset.section = "trends";

    wrapper.appendChild(
      createElement(
        "div",
        "rte-result-count",
        `${trends.length} research trend${trends.length === 1 ? "" : "s"} found`
      )
    );

    if (!trends.length) {
      wrapper.appendChild(
        createElement(
          "p",
          "rte-body",
          "No research trends were returned."
        )
      );
    }

    for (const trend of trends) {
      const details = createElement(
        "details",
        "rte-trend-card"
      );

      details.open = true;

      const summary = createElement(
        "summary",
        "",
        trend.name
        ||
        trend.nameEn
        ||
        trend.nameJa
        ||
        "Research trend"
      );

      if (trend.maturity) {
        summary.appendChild(
          createElement(
            "span",
            "rte-maturity",
            trend.maturity
          )
        );
      }

      details.appendChild(summary);

      const content = createElement(
        "div",
        "rte-trend-content"
      );

      if (trend.description) {
        content.appendChild(
          createElement(
            "p",
            "rte-body",
            trend.description
          )
        );
      }

      if (trend.whyImportantNow) {
        content.appendChild(
          createElement(
            "div",
            "rte-label",
            "Why it matters now"
          )
        );

        content.appendChild(
          createElement(
            "p",
            "rte-body",
            trend.whyImportantNow
          )
        );
      }

      if (
        Array.isArray(trend.researchQuestions)
        &&
        trend.researchQuestions.length
      ) {
        content.appendChild(
          createElement(
            "div",
            "rte-label",
            "Key research questions"
          )
        );

        const list = createElement(
          "ul",
          "rte-rq"
        );

        for (const question of trend.researchQuestions) {
          list.appendChild(
            createElement(
              "li",
              "",
              question
            )
          );
        }

        content.appendChild(list);
      }

      if (
        Array.isArray(trend.keywords)
        &&
        trend.keywords.length
      ) {
        const keywordRow = createElement(
          "div",
          "rte-keywords"
        );

        for (const keyword of trend.keywords) {
          keywordRow.appendChild(
            createElement(
              "span",
              "rte-keyword",
              keyword
            )
          );
        }

        content.appendChild(keywordRow);
      }

      const papers = Array.isArray(trend.papers)
        ? trend.papers
        : [];

      if (papers.length) {
        content.appendChild(
          createElement(
            "div",
            "rte-label",
            "Representative papers"
          )
        );

        for (const paper of papers) {
          content.appendChild(
            renderPaperCard(
              paper,
              "Representative Paper"
            )
          );
        }
      }

      details.appendChild(content);
      wrapper.appendChild(details);
    }

    panel.appendChild(wrapper);

    return true;
  }


  function renderWarnings(result) {
    const old = document.querySelector(
      "#rte-global-warnings"
    );

    if (old) {
      old.remove();
    }

    const warnings = Array.isArray(result.warnings)
      ? result.warnings
      : [];

    if (!warnings.length) {
      return;
    }

    const container = createElement(
      "section",
      "rte-fallback"
    );

    container.id = "rte-global-warnings";

    container.appendChild(
      createElement(
        "h2",
        "",
        "Search Notes"
      )
    );

    for (const warning of warnings) {
      container.appendChild(
        createElement(
          "div",
          "rte-warning",
          warning
        )
      );
    }

    document.body.appendChild(container);
  }


  function renderFallback(result) {
    let container = document.querySelector(
      "#rte-fallback-results"
    );

    if (container) {
      container.remove();
    }

    container = createElement(
      "section",
      "rte-fallback"
    );

    container.id = "rte-fallback-results";

    container.appendChild(
      createElement(
        "h2",
        "",
        "Research Results"
      )
    );

    const fp = createElement(
      "div",
      "rte-generated-results"
    );

    fp.appendChild(
      createElement(
        "h3",
        "",
        "Foundational Papers"
      )
    );

    for (const paper of (result.foundationalPapers || [])) {
      fp.appendChild(
        renderPaperCard(
          paper,
          "Foundational Paper"
        )
      );
    }

    container.appendChild(fp);

    const tr = createElement(
      "div",
      "rte-generated-results"
    );

    tr.appendChild(
      createElement(
        "h3",
        "",
        "Research Trends"
      )
    );

    for (const trend of (result.researchTrends || [])) {
      const details = createElement(
        "details",
        "rte-trend-card"
      );

      details.open = true;

      const summary = createElement(
        "summary",
        "",
        trend.name
        ||
        trend.nameEn
        ||
        trend.nameJa
        ||
        "Research trend"
      );

      details.appendChild(summary);

      const content = createElement(
        "div",
        "rte-trend-content"
      );

      if (trend.description) {
        content.appendChild(
          createElement(
            "p",
            "rte-body",
            trend.description
          )
        );
      }

      for (const paper of (trend.papers || [])) {
        content.appendChild(
          renderPaperCard(
            paper,
            "Representative Paper"
          )
        );
      }

      details.appendChild(content);
      tr.appendChild(details);
    }

    container.appendChild(tr);

    document.body.appendChild(container);
  }


  function renderResult(result, searchId = null) {
    if (!result) {
      return;
    }

    latestResult = result;

    translateUI();

    const foundationalRendered = renderFoundational(
      result
    );

    const trendsRendered = renderTrends(
      result
    );

    if (
      !foundationalRendered
      ||
      !trendsRendered
    ) {
      renderFallback(result);
    } else {
      const fallback = document.querySelector(
        "#rte-fallback-results"
      );

      if (fallback) {
        fallback.remove();
      }
    }

    renderWarnings(result);

    if (searchId) {
      renderedSearchId = searchId;
    }

    console.log(
      "Research Trend Explorer rendered result:",
      {
        searchId,
        foundationalPapers:
          (result.foundationalPapers || []).length,
        researchTrends:
          (result.researchTrends || []).length
      }
    );
  }


  async function loadSearchResult(searchId) {
    if (
      !searchId
      ||
      activeLoadId === searchId
    ) {
      return;
    }

    activeLoadId = searchId;

    try {
      const response = await nativeFetch(
        `/api/search/${encodeURIComponent(searchId)}`,
        {
          cache: "no-store"
        }
      );

      const payload = await response.json();

      if (
        payload
        &&
        payload.status === "completed"
        &&
        payload.result
      ) {
        latestSearchId = searchId;
        renderResult(
          payload.result,
          searchId
        );
      }
    } catch (error) {
      console.error(
        "Could not load research result:",
        error
      );
    } finally {
      activeLoadId = null;
    }
  }


  function scanSearchIdFromPage() {
    const text = (
      document.body
      &&
      document.body.innerText
    )
      || "";

    const matches = text.match(
      /[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/gi
    );

    if (
      matches
      &&
      matches.length
    ) {
      return matches[
        matches.length - 1
      ];
    }

    return null;
  }


  async function refreshFromVisibleSearchId() {
    const id = scanSearchIdFromPage();

    if (
      !id
      ||
      id === renderedSearchId
    ) {
      return;
    }

    await loadSearchResult(id);
  }


  // ----------------------------------------------------------
  // Intercept existing app.js fetch calls.
  // This captures the search ID even if the page text changes.
  // ----------------------------------------------------------

  window.fetch = async function(...args) {
    const response = await nativeFetch(...args);

    try {
      const requestUrl =
        typeof args[0] === "string"
          ? args[0]
          : (
              args[0]
              &&
              args[0].url
            )
            || "";

      const method =
        (
          args[1]
          &&
          args[1].method
        )
        ||
        (
          args[0]
          &&
          args[0].method
        )
        ||
        "GET";

      if (
        method.toUpperCase() === "POST"
        &&
        /¥/api¥/search¥/?$/.test(requestUrl)
      ) {
        response.clone().json()
          .then(payload => {
            if (
              payload
              &&
              payload.searchId
            ) {
              latestSearchId = payload.searchId;

              setTimeout(
                () => loadSearchResult(
                  payload.searchId
                ),
                50
              );
            }
          })
          .catch(() => {});
      }

      if (
        method.toUpperCase() === "GET"
        &&
        /¥/api¥/search¥/[^/?#]+/.test(requestUrl)
      ) {
        response.clone().json()
          .then(payload => {
            if (
              payload
              &&
              payload.status === "completed"
              &&
              payload.result
            ) {
              const parts = requestUrl.split("/");
              const id = parts[parts.length - 1];

              latestSearchId = id;

              setTimeout(
                () => renderResult(
                  payload.result,
                  id
                ),
                50
              );

              setTimeout(
                () => renderResult(
                  payload.result,
                  id
                ),
                350
              );
            }
          })
          .catch(() => {});
      }
    } catch (error) {
      console.error(
        "Fetch hook error:",
        error
      );
    }

    return response;
  };


  // ----------------------------------------------------------
  // Mutation / timer fallback.
  // Even if the existing app.js behaves unexpectedly, the visible
  // UUID is detected and the already-completed local API result is
  // loaded without calling OpenAI again.
  // ----------------------------------------------------------

  let observerTimer = null;

  const observer = new MutationObserver(
    () => {
      translateUI();

      clearTimeout(observerTimer);

      observerTimer = setTimeout(
        () => {
          refreshFromVisibleSearchId();

          if (
            latestResult
            &&
            (
              !document.querySelector(
                ".rte-generated-results[data-section='foundational']"
              )
              ||
              !document.querySelector(
                ".rte-generated-results[data-section='trends']"
              )
            )
          ) {
            renderResult(
              latestResult,
              latestSearchId
            );
          }
        },
        120
      );
    }
  );


  document.addEventListener(
    "DOMContentLoaded",
    () => {
      translateUI();

      observer.observe(
        document.body,
        {
          childList: true,
          subtree: true,
          characterData: true
        }
      );

      refreshFromVisibleSearchId();

      setInterval(
        refreshFromVisibleSearchId,
        1000
      );
    }
  );
})();
</script>
"""



# ============================================================
# Root
# ============================================================

@app.get(
    "/",
    response_class=HTMLResponse,
)
def read_root() -> HTMLResponse:

    index_path = (
        STATIC_DIR
        /
        "index.html"
    )

    html = index_path.read_text(
        encoding="utf-8"
    )

    if "</body>" in html:
        html = html.replace(
            "</body>",
            UI_PATCH
            +
            "¥n</body>",
        )
    else:
        html += UI_PATCH

    return HTMLResponse(
        content=html,
        headers={
            "Content-Type":
                "text/html; charset=utf-8"
        },
    )


# ============================================================
# Search
# ============================================================

@app.post(
    "/api/search",
    response_model=dict,
)
def create_search(
    request: SearchRequest,
) -> dict:

    search_id = str(
        uuid.uuid4()
    )

    try:
        # The current frontend performs only one GET after POST.
        # Complete the API research request before returning searchId.
        result = research_topic(
            request
        )

        result[
            "searchMetadata"
        ][
            "searchId"
        ] = search_id

        item = {
            "status":
                "completed",

            "progress":
                "Search results ready",

            "result":
                result,

            "error":
                None,
        }

        search_store[
            search_id
        ] = item

        save_search(
            search_id,
            item,
        )

    except Exception as exc:
        print(
            "SEARCH ERROR:",
            type(exc).__name__,
            repr(str(exc)),
        )

        item = {
            "status":
                "error",

            "progress":
                "An error occurred during the search",

            "result":
                {},

            "error":
                str(exc),
        }

        search_store[
            search_id
        ] = item

        save_search(
            search_id,
            item,
        )

    return {
        "searchId":
            search_id
    }


# ============================================================
# Search result
# ============================================================

@app.get(
    "/api/search/{search_id}",
    response_model=SearchStatusResponse,
)
def get_search(
    search_id: str,
) -> SearchStatusResponse:

    item = search_store.get(
        search_id
    )

    # Recover searches after uvicorn restart.
    if item is None:
        item = load_search(
            search_id
        )

        if item is not None:
            search_store[
                search_id
            ] = item

    # Do not return HTTP 404 for an old browser-stored ID.
    if item is None:
        return SearchStatusResponse(
            status="error",
            progress="Search result unavailable",
            result={},
            error=(
                "This search ID is no longer available. "
                "Please start a new search."
            ),
        )

    return SearchStatusResponse(
        **item
    )


# ============================================================
# Health
# ============================================================

@app.get("/api/health")
def health() -> dict:

    return {
        "ok":
            True,

        "apiKeyConfigured":
            get_openai_api_key()
            is not None,

        "defaultModel":
            MODEL_NAME,

        "searchModel":
            SEARCH_MODEL_NAME,

        "maxWebSearchCalls":
            MAX_WEB_SEARCH_CALLS,

        "outputLanguage":
            "English",

        "persistentSearchCache":
            True,

        "frontendRendererPatch":
            True,
    }
