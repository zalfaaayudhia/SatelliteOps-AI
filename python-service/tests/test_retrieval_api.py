
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_retrieve_returns_results(monkeypatch):
    def fake_search_documents(query, n_results):
        return [
            {
                "text": "Review telemetry and record the anomaly.",
                "source": "incident_response.md",
                "chunk_index": 0,
                "distance": 0.25,
            }
        ]

    monkeypatch.setattr(
        "app.main.search_documents",
        fake_search_documents,
    )

    response = client.post(
        "/retrieve",
        json={
            "query": "How do I investigate an anomaly?",
            "top_k": 3,
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["result_count"] == 1
    assert data["results"][0]["source"] == "incident_response.md"
    assert data["results"][0]["distance"] == 0.25


def test_retrieve_rejects_empty_query():
    response = client.post(
        "/retrieve",
        json={"query": "", "top_k": 3},
    )

    assert response.status_code == 422


def test_retrieve_rejects_invalid_top_k():
    response = client.post(
        "/retrieve",
        json={
            "query": "Satellite health",
            "top_k": 100,
        },
    )

    assert response.status_code == 422
