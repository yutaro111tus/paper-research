from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_search_endpoint_returns_search_id_and_result():
    response = client.post(
        "/api/search",
        json={
            "query": "generative AI in education",
            "field": "情報科学",
            "foundationalCount": 3,
            "trendCount": 5,
            "papersPerTrend": 3,
            "recentYears": 5,
            "languages": ["ja", "en"],
            "publicationTypes": ["article"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "searchId" in payload

    search_id = payload["searchId"]
    status_response = client.get(f"/api/search/{search_id}")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "completed"
    assert status_payload["result"]["querySummary"]["originalQuery"] == "generative AI in education"
