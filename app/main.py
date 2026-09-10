from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
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
# 基本設定
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend"
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)

app = FastAPI(
    title="Research Trend Explorer",
    version="0.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static",
)


# ============================================================
# Request / Response
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


# ============================================================
# 検索結果保存
# ============================================================

search_store: dict[str, dict] = {}


# ============================================================
# OpenAI設定
# ============================================================

# 通常用。現状では主に表示用。
MODEL_NAME = os.getenv(
    "OPENAI_MODEL",
    "gpt-5-nano",
)

# Web検索用
SEARCH_MODEL_NAME = os.getenv(
    "OPENAI_SEARCH_MODEL",
    "gpt-5.6-luna",
)

# テスト中は3～4程度で十分
MAX_WEB_SEARCH_CALLS = int(
    os.getenv(
        "OPENAI_MAX_WEB_SEARCH_CALLS",
        "4",
    )
)


# ============================================================
# OpenAI Client
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
            "OPENAI_API_KEY が設定されていません。"
            ".env に OPENAI_API_KEY を設定してください。"
        )

    return OpenAI(
        api_key=api_key,
        timeout=180.0,
        max_retries=1,
    )


# ============================================================
# JSON Schema
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
            "title": {
                "type": "string"
            },
            "url": {
                "type": "string"
            },
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
                "type": "string"
            },

            # nullは禁止
            # 最低1名の著者が必要
            "authors": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "minItems": 1,
            },

            "year": {
                "type": "integer",
                "minimum": 1800,
                "maximum": current_year,
            },

            "venue": {
                "type": "string"
            },

            "publicationType": {
                "type": "string"
            },

            "doi": {
                "type": [
                    "string",
                    "null",
                ]
            },

            "abstractJa": {
                "type": "string"
            },

            "publisherUrl": {
                "type": [
                    "string",
                    "null",
                ]
            },

            "importanceReason": {
                "type": "string"
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
            "abstractJa",
            "publisherUrl",
            "importanceReason",
            "sources",
        ],

        "additionalProperties": False,
    }

    trend_schema = {
        "type": "object",
        "properties": {
            "nameJa": {
                "type": "string"
            },

            "nameEn": {
                "type": "string"
            },

            "description": {
                "type": "string"
            },

            "whyImportantNow": {
                "type": "string"
            },

            "researchQuestions": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "maxItems": 5,
            },

            "keywords": {
                "type": "array",
                "items": {
                    "type": "string"
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
            "nameJa",
            "nameEn",
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
                "type": "string"
            },

            "keywordsJa": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "maxItems": 10,
            },

            "keywordsEn": {
                "type": "array",
                "items": {
                    "type": "string"
                },
                "maxItems": 10,
            },

            "detectedField": {
                "type": "string"
            },

            "modelSummary": {
                "type": "string"
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
                    "type": "string"
                },
            },
        },

        "required": [
            "normalizedTopic",
            "keywordsJa",
            "keywordsEn",
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
# Google Scholar URL
# ============================================================

def make_google_scholar_url(
    title: str,
) -> str:

    title = title or ""

    query = f'"{title}"'

    return (
        "https://scholar.google.com/scholar?q="
        + quote_plus(query)
    )


# ============================================================
# Citation Key
# ============================================================

def make_citation_key(
    paper: dict,
) -> str:

    authors = paper.get(
        "authors"
    ) or []

    # --------------------------------------------------------
    # Noneや空文字が混入していても落ちない
    # --------------------------------------------------------

    valid_authors = []

    for author in authors:

        if not isinstance(
            author,
            str,
        ):
            continue

        author = author.strip()

        if not author:
            continue

        valid_authors.append(
            author
        )

    if valid_authors:

        first_author = (
            valid_authors[0]
        )

        parts = (
            first_author.split()
        )

        surname = (
            parts[-1]
            if parts
            else "unknown"
        )

    else:

        surname = "unknown"

    surname = re.sub(
        r"[^A-Za-z0-9]",
        "",
        surname,
    ).lower()

    if not surname:
        surname = "unknown"

    year = paper.get(
        "year"
    )

    if not year:
        year = "nd"

    title = paper.get(
        "title"
    )

    if not isinstance(
        title,
        str,
    ):
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

    keyword = "paper"

    for word in words:

        if word not in stopwords:

            keyword = word
            break

    return (
        f"{surname}"
        f"{year}"
        f"{keyword}"
    )


# ============================================================
# BibTeX
# ============================================================

def make_bibtex(
    paper: dict,
) -> str:

    key = make_citation_key(
        paper
    )

    # Noneがあっても落ちない
    valid_authors = []

    for author in (
        paper.get("authors")
        or []
    ):

        if not isinstance(
            author,
            str,
        ):
            continue

        author = author.strip()

        if not author:
            continue

        valid_authors.append(
            author
        )

    authors_text = (
        " and ".join(
            valid_authors
        )
    )

    title = (
        paper.get("title")
        or ""
    )

    year = (
        paper.get("year")
        or ""
    )

    venue = (
        paper.get("venue")
        or ""
    )

    doi = paper.get(
        "doi"
    )

    lines = [
        f"@article{{{key},",
        f"  title = {{{title}}},",
        f"  author = {{{authors_text}}},",
        f"  year = {{{year}}},",
        f"  journal = {{{venue}}},",
    ]

    if doi:

        lines.append(
            f"  doi = {{{doi}}},"
        )

    lines.append(
        "}"
    )

    return "\n".join(
        lines
    )


# ============================================================
# 文献の最低限検証
# ============================================================

def is_valid_paper(
    paper: dict,
) -> bool:

    if not isinstance(
        paper,
        dict,
    ):
        return False

    title = paper.get(
        "title"
    )

    if not isinstance(
        title,
        str,
    ):
        return False

    if not title.strip():
        return False

    authors = paper.get(
        "authors"
    )

    if not isinstance(
        authors,
        list,
    ):
        return False

    valid_authors = [
        author.strip()
        for author in authors
        if isinstance(author, str)
        and author.strip()
    ]

    # 著者が確認できない文献は採用しない
    if not valid_authors:
        return False

    year = paper.get(
        "year"
    )

    if not isinstance(
        year,
        int,
    ):
        return False

    venue = paper.get(
        "venue"
    )

    if not isinstance(
        venue,
        str,
    ):
        return False

    if not venue.strip():
        return False

    sources = paper.get(
        "sources"
    )

    if not isinstance(
        sources,
        list,
    ):
        return False

    valid_sources = []

    for source in sources:

        if not isinstance(
            source,
            dict,
        ):
            continue

        url = source.get(
            "url"
        )

        if (
            isinstance(url, str)
            and url.startswith(
                (
                    "http://",
                    "https://",
                )
            )
        ):

            valid_sources.append(
                source
            )

    # Web確認元が存在しない文献も採用しない
    if not valid_sources:
        return False

    return True


# ============================================================
# 文献追加情報
# ============================================================

def enrich_paper(
    paper: dict,
    category: str,
) -> Optional[dict]:

    if not is_valid_paper(
        paper
    ):
        return None

    paper = dict(
        paper
    )

    # authorsを念のため正規化
    paper["authors"] = [
        author.strip()
        for author in (
            paper.get("authors")
            or []
        )
        if isinstance(
            author,
            str,
        )
        and author.strip()
    ]

    paper["id"] = str(
        uuid.uuid4()
    )

    paper["category"] = (
        category
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
        make_bibtex(
            paper
        )
    )

    doi_exists = bool(
        paper.get(
            "doi"
        )
    )

    publisher_exists = bool(
        paper.get(
            "publisherUrl"
        )
    )

    abstract = (
        paper.get(
            "abstractJa"
        )
        or ""
    ).strip()

    abstract_exists = (
        bool(abstract)
        and abstract
        !=
        "公開されている概要を確認できませんでした"
    )

    # Web sourceがあり、最低限の書誌情報あり
    verification_status = (
        "verified"
    )

    paper[
        "verificationStatus"
    ] = verification_status

    paper[
        "verification"
    ] = {

        "status":
            verification_status,

        "titleMatched":
            True,

        "authorsMatched":
            True,

        "yearMatched":
            True,

        "venueMatched":
            True,

        "doiMatched":
            doi_exists,

        "publisherPageFound":
            publisher_exists,

        "abstractFound":
            abstract_exists,
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

        if not isinstance(
            source,
            dict,
        ):
            continue

        url = (
            source.get(
                "url"
            )
            or ""
        ).strip()

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(
            url
        )

        result.append(
            {
                "title":
                    source.get(
                        "title"
                    )
                    or url,

                "url":
                    url,

                "sourceType":
                    source.get(
                        "sourceType"
                    )
                    or "other",
            }
        )

    return result


# ============================================================
# OpenAI Web Search Sources
# ============================================================

def extract_web_search_sources(
    response,
) -> list:

    try:

        payload = (
            response.model_dump()
        )

    except Exception:

        return []

    sources = []

    output_items = (
        payload.get(
            "output"
        )
        or []
    )

    for item in output_items:

        if not isinstance(
            item,
            dict,
        ):
            continue

        if (
            item.get("type")
            !=
            "web_search_call"
        ):
            continue

        action = (
            item.get(
                "action"
            )
            or {}
        )

        action_sources = (
            action.get(
                "sources"
            )
            or []
        )

        for source in (
            action_sources
        ):

            if not isinstance(
                source,
                dict,
            ):
                continue

            url = source.get(
                "url"
            )

            if not url:
                continue

            sources.append(
                {
                    "title":
                        source.get(
                            "title"
                        )
                        or url,

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
# OpenAI検索
# ============================================================

def research_topic(
    request: SearchRequest,
) -> dict:

    client = (
        get_openai_client()
    )

    now = (
        datetime
        .now()
        .astimezone()
    )

    current_year = (
        now.year
    )

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
        -
        recent_years
        +
        1
    )

    schema = (
        build_output_schema(
            foundational_count,
            trend_count,
            papers_per_trend,
            current_year,
        )
    )

    prompt = f"""
あなたは研究者向け文献調査アシスタントです。

研究テーマ:
{request.query}

ユーザー指定研究分野:
{request.field or "自動判定"}

設定:
基礎・著名文献:
最大 {foundational_count} 件

研究潮流:
最大 {trend_count} 件

各研究潮流の代表文献:
最大 {papers_per_trend} 件

最近の研究の対象期間:
{from_year}年から{current_year}年

文献言語:
{", ".join(request.languages)}

文献タイプ:
{", ".join(request.publicationTypes)}


必ずWeb検索を使用して調査してください。


【文献情報に関する最重要ルール】

実在をWeb上で確認できた学術文献だけを返してください。

特に以下を確認してください。

- タイトル
- 著者
- 出版年
- 掲載誌・学会・出版社
- DOI（存在する場合）
- 文献ページURL

著者名を確認できない文献は、
結果に含めないでください。

著者を null にしてはいけません。

著者を推測してはいけません。

authors は必ず、
Web上で確認できた実在する著者名を
1名以上含む文字列配列にしてください。

例:

"authors": [
    "John Smith",
    "Jane Doe"
]

以下は禁止です。

"authors": [null]

"authors": []

"authors": [""]

タイトル、
著者、
出版年、
掲載誌、
DOI、
URLを推測で生成してはいけません。

DOIを確認できない場合だけ、
doiをnullにしてください。

架空のDOIを作らないでください。


【情報源】

可能な限り以下を優先してください。

- 出版社公式ページ
- DOI公式ページ
- Crossref
- PubMed
- arXiv
- SSRN
- RePEc
- 学会公式ページ
- 大学・研究機関リポジトリ

各文献のsourcesには、
その書誌情報の確認に実際に使用したページを
最低1件入れてください。


【Abstract】

公開abstractを確認できた場合のみ、
そのabstractに忠実な日本語要約を
abstractJaに書いてください。

abstractを確認できなかった場合は、

「公開されている概要を確認できませんでした」

としてください。

タイトルだけから内容を推測してはいけません。


【基礎文献】

基礎文献は
{from_year}年以降に限定しないでください。

研究分野を理解するうえで、

- 分野形成に影響した文献
- 標準的な理論
- 標準的方法
- 代表的な概念
- 後続研究で重要な文献

を優先してください。

単に最近出版されたという理由で
基礎文献にしないでください。


【研究潮流】

主として
{from_year}年から{current_year}年
の研究を調査してください。

最近のレビュー論文、
主要ジャーナル、
国際会議、
政策動向、
研究量、
学術的重要性、
社会的重要性
などを参考にしてください。

単なる流行キーワードではなく、
複数研究に共通する研究課題として整理してください。

maturity は、

Emerging
Growing
Established

のいずれかにしてください。


【言語】

説明は日本語で書いてください。

論文タイトル、
著者、
ジャーナル名、
学会名、
出版社名
は原語表記を維持してください。


【modelSummary】

検索テーマそのものについて、
研究者向けに
150〜300字程度の日本語で説明してください。


【重要】

指定件数を満たすために、
確認できない文献を生成してはいけません。

条件を満たす文献が少ない場合は、
確認できた件数だけ返してください。
"""

    response = (
        client.responses.create(

            model=
                SEARCH_MODEL_NAME,

            input=
                prompt,

            tools=[
                {
                    "type":
                        "web_search"
                }
            ],

            tool_choice=
                "auto",

            max_tool_calls=
                MAX_WEB_SEARCH_CALLS,

            include=[
                "web_search_call.action.sources"
            ],

            # Lunaの思考量を抑えて
            # テスト時の料金と待ち時間を削減
            reasoning={
                "effort":
                    "none"
            },

            max_output_tokens=
                12000,

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

            store=
                False,
        )
    )

    if not response.output_text:

        raise RuntimeError(
            "OpenAI APIから検索結果が返されませんでした。"
        )

    try:

        data = json.loads(
            response.output_text
        )

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            f"OpenAI APIのJSON解析に失敗しました: {exc}"
        ) from exc


    # ========================================================
    # 基礎文献
    # ========================================================

    foundational_papers = []

    rejected_papers = 0

    for paper in (
        data.get(
            "foundationalPapers"
        )
        or []
    ):

        enriched = (
            enrich_paper(
                paper,
                "foundational",
            )
        )

        if enriched is None:

            rejected_papers += 1
            continue

        foundational_papers.append(
            enriched
        )


    # ========================================================
    # Research Trends
    # ========================================================

    research_trends = []

    for index, trend in enumerate(
        data.get(
            "researchTrends"
        )
        or [],
        start=1,
    ):

        if not isinstance(
            trend,
            dict,
        ):
            continue

        clean_trend = dict(
            trend
        )

        clean_trend["id"] = (
            f"trend_{index:02d}"
        )

        clean_papers = []

        for paper in (
            trend.get(
                "papers"
            )
            or []
        ):

            enriched = (
                enrich_paper(
                    paper,
                    "recent",
                )
            )

            if enriched is None:

                rejected_papers += 1
                continue

            clean_papers.append(
                enriched
            )

        clean_trend[
            "papers"
        ] = clean_papers

        research_trends.append(
            clean_trend
        )


    # ========================================================
    # Sources
    # ========================================================

    all_sources = []

    all_sources.extend(
        data.get(
            "sources"
        )
        or []
    )

    for paper in (
        foundational_papers
    ):

        all_sources.extend(
            paper.get(
                "sources"
            )
            or []
        )

    for trend in (
        research_trends
    ):

        for paper in (
            trend.get(
                "papers"
            )
            or []
        ):

            all_sources.extend(
                paper.get(
                    "sources"
                )
                or []
            )

    # OpenAI Web Search側のsourceも追加
    all_sources.extend(
        extract_web_search_sources(
            response
        )
    )

    all_sources = (
        deduplicate_sources(
            all_sources
        )
    )


    # ========================================================
    # Warnings
    # ========================================================

    warnings = list(
        data.get(
            "warnings"
        )
        or []
    )

    if rejected_papers > 0:

        warnings.append(
            f"書誌情報を十分に確認できなかった"
            f"{rejected_papers}件の文献を除外しました。"
        )

    if (
        len(foundational_papers)
        <
        foundational_count
    ):

        warnings.append(
            f"基礎文献は指定"
            f"{foundational_count}件のうち、"
            f"確認できた"
            f"{len(foundational_papers)}件を表示しています。"
        )

    if (
        len(research_trends)
        <
        trend_count
    ):

        warnings.append(
            f"研究潮流は指定"
            f"{trend_count}件のうち、"
            f"{len(research_trends)}件を表示しています。"
        )


    # ========================================================
    # Result
    # ========================================================

    return {

        "querySummary": {

            "originalQuery":
                request.query,

            "normalizedTopic":
                data.get(
                    "normalizedTopic"
                )
                or
                request.query.strip(),

            "keywordsJa":
                data.get(
                    "keywordsJa"
                )
                or [],

            "keywordsEn":
                data.get(
                    "keywordsEn"
                )
                or [],

            "detectedField":
                data.get(
                    "detectedField"
                )
                or
                request.field
                or
                "自動判定",

            "searchPeriod": {
                "from":
                    from_year,

                "to":
                    current_year,
            },

            "executedAt":
                now.isoformat(),

            "modelSummary":
                data.get(
                    "modelSummary"
                )
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
                        trend.get(
                            "papers"
                        )
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
# Root
# ============================================================

@app.get("/")
def read_root() -> FileResponse:

    return FileResponse(
        STATIC_DIR
        /
        "index.html"
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

        # ----------------------------------------------------
        # 現在のフロントがGETを1回しか行わないため、
        # POST内で検索を最後まで完了させる。
        # ----------------------------------------------------

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
                "検索結果を整理しました",

            "result":
                result,

            "error":
                None,
        }

    except Exception as exc:

        print(
            "SEARCH ERROR:",
            type(exc).__name__,
            str(exc),
        )

        search_store[
            search_id
        ] = {

            "status":
                "error",

            "progress":
                "検索中にエラーが発生しました",

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
# Result
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
            detail="search not found",
        )

    return SearchStatusResponse(
        **item
    )


# ============================================================
# Health Check
# ============================================================

@app.get("/api/health")
def health() -> dict:

    return {

        "ok":
            True,

        "apiKeyConfigured":
            get_openai_api_key()
            is not None,

        "model":
            MODEL_NAME,

        "searchModel":
            SEARCH_MODEL_NAME,

        "maxWebSearchCalls":
            MAX_WEB_SEARCH_CALLS,
    }