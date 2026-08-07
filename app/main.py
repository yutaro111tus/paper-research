from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend"

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


@app.get("/")
def read_root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/search", response_model=dict)
def create_search(request: SearchRequest) -> dict:
    search_id = str(uuid.uuid4())
    result = {
        "querySummary": {
            "originalQuery": request.query,
            "normalizedTopic": request.query.strip(),
            "keywordsJa": [request.query],
            "keywordsEn": [request.query],
            "detectedField": request.field or "自動判定",
            "searchPeriod": {"from": datetime.now().year - request.recentYears, "to": datetime.now().year},
            "executedAt": datetime.now().isoformat(),
        },
        "foundationalPapers": [],
        "researchTrends": [],
        "sources": [],
        "warnings": [],
        "searchMetadata": {
            "searchId": search_id,
            "status": "completed",
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
