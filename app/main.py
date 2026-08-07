from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend"
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)

app = FastAPI(title="Research Trend Explorer", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


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


MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5-nano")


def get_openai_api_key() -> Optional[str]:
    value = os.getenv("OPENAI_API_KEY", "").strip()
    return value or None


def get_openai_client() -> Optional[OpenAI]:
    api_key = get_openai_api_key()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def summarize_query(query: str, field: Optional[str]) -> str:
    client = get_openai_client()
    if client is None:
        return "OpenAI API key is not configured. Set OPENAI_API_KEY in the local environment to enable model-based summaries."

    prompt = (
        f"You are helping a user understand a research topic. "
        f"Summarize the topic '{query}' in Japanese in 2 short bullet points. "
        f"The field is {field or 'unspecified'}."
    )
    completion = client.responses.create(
        model=MODEL_NAME,
        input=prompt,
    )
    return completion.output_text.strip()


@app.get("/")
def read_root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/search", response_model=dict)
def create_search(request: SearchRequest) -> dict:
    search_id = str(uuid.uuid4())
    summary = summarize_query(request.query, request.field)
    result = {
        "querySummary": {
            "originalQuery": request.query,
            "normalizedTopic": request.query.strip(),
            "keywordsJa": [request.query],
            "keywordsEn": [request.query],
            "detectedField": request.field or "自動判定",
            "searchPeriod": {"from": datetime.now().year - request.recentYears, "to": datetime.now().year},
            "executedAt": datetime.now().isoformat(),
            "modelSummary": summary,
        },
        "foundationalPapers": [],
        "researchTrends": [],
        "sources": [],
        "warnings": [],
        "searchMetadata": {
            "searchId": search_id,
            "status": "completed",
            "modelName": MODEL_NAME,
        },
    }
    search_store[search_id] = {
        "status": "completed",
        "progress": "検索結果を整理しました",
        "result": result,
        "error": None,
    }
    return {"searchId": search_id}


@app.get("/api/search/{search_id}", response_model=SearchStatusResponse)
def get_search(search_id: str) -> SearchStatusResponse:
    item = search_store.get(search_id)
    if not item:
        raise HTTPException(status_code=404, detail="search not found")
    return SearchStatusResponse(**item)
