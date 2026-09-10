from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from openai import OpenAI


# ============================================================
# Paths / environment
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend"
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)


# ============================================================
# JSON response
# ============================================================

class SafeJSONResponse(JSONResponse):
    """
    Serialize non-ASCII characters as ¥¥uXXXX.
    This makes the actual HTTP JSON payload ASCII-only and avoids
    browser/terminal charset problems while JSON clients still receive
    the correct Unicode values after parsing.
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
# Input normalization
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
    if not field:
        return "Auto-detect"
    return FIELD_MAP.get(field, field)


# ============================================================
# Structured Output JSON schema
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
                "minLength": 1,
            },
            "authors": {
                "type": "array",
                "items": {
                    "type": "string",
                    "minLength": 1,
                },
                "minItems": 1,
            },
            "year": {
                "type": "integer",
                "minimum": 1800,
                "maximum": current_year,
            },
            "venue": {
                "type": "string",
                "minLength": 1,
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
                "minItems": 1,
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
                "maxItems": 5,
            },
            "keywords": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "maxItems": 10,
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
                "maxItems": papers_per_trend,
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
                "maxItems": 12,
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
                "maxItems": foundational_count,
            },
            "researchTrends": {
                "type": "array",
                "items": trend_schema,
                "maxItems": trend_count,
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
    query = f'"{title or ""}"'
    return (
        "https://scholar.google.com/scholar?q="
        + quote_plus(query)
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
        "a",
        "an",
        "the",
        "of",
        "and",
        "or",
        "for",
        "to",
        "in",
        "on",
        "with",
        "from",
        "by",
        "at",
        "as",
        "is",
        "are",
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


def make_bibtex(paper: dict) -> str:
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


def is_valid_paper(paper: dict) -> bool:
    if not isinstance(paper, dict):
        return False

    title = paper.get("title")
    if not isinstance(title, str) or not title.strip():
        return False

    authors = paper.get("authors") or []
    if not isinstance(authors, list):
        return False

    valid_authors = [
        author
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

    sources = paper.get("sources") or []
    if not isinstance(sources, list):
        return False

    valid_source_found = False

    for source in sources:
        if not isinstance(source, dict):
            continue

        url = source.get("url")

        if (
            isinstance(url, str)
            and url.startswith(
                (
                    "https://",
                    "http://",
                )
            )
        ):
            valid_source_found = True
            break

    return valid_source_found


def enrich_paper(
    paper: dict,
    category: str,
) -> Optional[dict]:

    if not is_valid_paper(paper):
        return None

    paper = dict(paper)

    paper["authors"] = [
        author.strip()
        for author in paper.get("authors", [])
        if isinstance(author, str)
        and author.strip()
    ]

    paper["id"] = str(uuid.uuid4())
    paper["category"] = category

    # Keep both names for compatibility with the existing frontend.
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

    paper["bibtex"] = make_bibtex(
        paper
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
        and abstract_text
        !=
        "No publicly available abstract was verified."
    )

    paper["verificationStatus"] = (
        "verified"
    )

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

def deduplicate_sources(
    sources: list,
) -> list:

    result = []
    seen_urls = set()

    for source in sources:
        if not isinstance(source, dict):
            continue

        url = (
            source.get("url")
            or ""
        ).strip()

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        source_title = source.get("title") or "Source"
        if not isinstance(source_title, str) or not source_title.isascii():
            source_title = "Source"

        result.append(
            {
                "title":
                    source_title,

                "url":
                    url,

                "sourceType":
                    source.get("sourceType")
                    or "other",
            }
        )

    return result


def extract_web_search_sources(
    response,
) -> list:

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
                    "title":
                        "Web source",

                    "url":
                        url,

                    "sourceType":
                        "other",
                }
            )

    return deduplicate_sources(
        sources
    )


# ============================================================
# OpenAI research
# ============================================================

def research_topic(
    request: SearchRequest,
) -> dict:

    client = get_openai_client()

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
{request.query}

USER-SPECIFIED FIELD:
{field}

SETTINGS:
- Foundational papers: up to {foundational_count}
- Research trends: up to {trend_count}
- Representative papers per trend: up to {papers_per_trend}
- Recent research period: {from_year}-{current_year}

Use web search to investigate the topic.

OUTPUT LANGUAGE RULE:
EVERY human-readable text field in your JSON response MUST be in English.

This includes:
- normalizedTopic
- keywords
- detectedField
- modelSummary
- trend names
- trend descriptions
- research questions
- importance explanations
- warnings
- source titles

The user query may be Japanese or another language.
Translate and normalize it internally, but return the topic in English.

PAPER LANGUAGE RULE:
Prefer papers with an official English bibliographic title.
If a paper has no verifiable English bibliographic title, exclude it.
Do not translate a paper title yourself.

BIBLIOGRAPHIC ACCURACY:
Only return papers whose existence you verified on the web.

Never invent or infer:
- paper title
- authors
- publication year
- journal/conference/publisher
- DOI
- paper URL

Authors are mandatory.
If you cannot verify at least one author, exclude the paper.
Never return an empty authors array.

Use authoritative sources when possible:
- official publisher page
- DOI page
- Crossref
- PubMed
- arXiv
- SSRN
- RePEc
- conference website
- university or research institute repository

DOI:
If a DOI cannot be verified, use null.
Never fabricate a DOI.

ABSTRACT:
If you can verify a publicly available abstract, summarize it faithfully
in concise English.

If no public abstract can be verified, set abstract exactly to:

"No publicly available abstract was verified."

Do not infer an abstract from the title.

FOUNDATIONAL PAPERS:
Do not restrict foundational papers to {from_year}-{current_year}.
Choose papers that are genuinely useful for understanding the formation,
standard theories, standard methods, or key concepts of the field.
Do not simply choose recent papers.

RESEARCH TRENDS:
Use mainly literature from {from_year}-{current_year}.
Identify genuine recurring research themes rather than isolated buzzwords.
Use recent reviews, major journals, conferences, and relevant policy or
societal developments where useful.

Maturity must be one of:
- Emerging
- Growing
- Established

MODEL SUMMARY:
Write a concise 100-180 word English overview of the research topic.

SOURCES:
Each paper must have at least one real web source used to verify its
bibliographic information.

If fewer verified papers are available than requested, return fewer papers.
Accuracy is more important than filling quotas.
"""

    response = client.responses.create(
        model=SEARCH_MODEL_NAME,
        input=prompt,

        tools=[
            {
                "type":
                    "web_search"
            }
        ],

        tool_choice="auto",

        max_tool_calls=
            MAX_WEB_SEARCH_CALLS,

        include=[
            "web_search_call.action.sources"
        ],

        reasoning={
            "effort":
                "none"
        },

        max_output_tokens=10000,

        text={
            "format": {
                "type":
                    "json_schema",

                "name":
                    "research_trend_explorer",

                "strict":
                    True,

                "schema":
                    schema,
            },

            "verbosity":
                "low",
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

        # Existing frontend compatibility
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

        clean_trend["papers"] = (
            clean_papers
        )

        research_trends.append(
            clean_trend
        )

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

    warnings = list(
        data.get("warnings")
        or []
    )

    if rejected_papers:
        warnings.append(
            f"{rejected_papers} paper(s) were excluded because "
            "their bibliographic information could not be validated."
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
            f"{len(research_trends)} verified trend(s) are shown."
        )

    keywords = (
        data.get("keywords")
        or []
    )

    normalized_topic = (
        data.get("normalizedTopic")
        or "Research topic"
    )

    return {
        "querySummary": {
            # Do not echo a Japanese query back into the UI.
            # Keep visible output English-only.
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
                "from":
                    from_year,

                "to":
                    current_year,
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
# English UI injection
# ============================================================

ENGLISH_UI_SCRIPT = r"""
<script>
(() => {
  const translations = new Map([
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

    ["検索結果を整理しました",
     "Search results ready"],

    ["検索中にエラーが発生しました",
     "An error occurred during the search"],

    ["まだ基礎文献データはありません",
     "No foundational papers yet"],

    ["検索結果の中から、分野理解に重要な文献を整理します。",
     "Important literature for understanding the field will appear here."],

    ["まだ研究潮流データはありません",
     "No research trends yet"],

    ["現在注目されているテーマを、成熟度ごとに整理します。",
     "Current research themes will appear here."],

    ["分野:",
     "Field:"],

    ["検索期間:",
     "Search period:"],

    ["モデル要約はまだありません。",
     "No research summary yet."]
  ]);

  function translateText(text) {
    const trimmed = text.trim();

    if (translations.has(trimmed)) {
      return text.replace(
        trimmed,
        translations.get(trimmed)
      );
    }

    return text;
  }

  function translateNode(root) {
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT
    );

    const nodes = [];

    while (walker.nextNode()) {
      nodes.push(walker.currentNode);
    }

    for (const node of nodes) {
      const translated = translateText(
        node.nodeValue || ""
      );

      if (translated !== node.nodeValue) {
        node.nodeValue = translated;
      }
    }

    if (root.querySelectorAll) {
      for (const el of root.querySelectorAll(
        "input, textarea"
      )) {
        if (
          el.placeholder
          &&
          translations.has(
            el.placeholder.trim()
          )
        ) {
          el.placeholder = translations.get(
            el.placeholder.trim()
          );
        }
      }

      for (const option of root.querySelectorAll(
        "option"
      )) {
        const key = option.textContent.trim();

        if (translations.has(key)) {
          option.textContent = translations.get(
            key
          );
        }
      }
    }
  }

  function run() {
    translateNode(document.body);
  }

  document.addEventListener(
    "DOMContentLoaded",
    run
  );

  const observer = new MutationObserver(
    () => run()
  );

  observer.observe(
    document.documentElement,
    {
      childList: true,
      subtree: true,
      characterData: true
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
            ENGLISH_UI_SCRIPT
            +
            "¥n</body>",
        )
    else:
        html += ENGLISH_UI_SCRIPT

    return HTMLResponse(
        content=html,
        media_type="text/html",
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
        # Run the complete research request here.
        # The existing frontend only performs one GET after POST.
        result = research_topic(
            request
        )

        result[
            "searchMetadata"
        ][
            "searchId"
        ] = search_id

        search_store[
            search_id
        ] = {
            "status":
                "completed",

            "progress":
                "Search results ready",

            "result":
                result,

            "error":
                None,
        }

    except Exception as exc:
        print(
            "SEARCH ERROR:",
            type(exc).__name__,
            repr(str(exc)),
        )

        search_store[
            search_id
        ] = {
            "status":
                "error",

            "progress":
                "An error occurred during the search",

            "result":
                {},

            "error":
                str(exc),
        }

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

    if not item:
        raise HTTPException(
            status_code=404,
            detail="Search not found",
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
    }
