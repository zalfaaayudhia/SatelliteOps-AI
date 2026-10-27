
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_answer_returns_grounded_response(monkeypatch):
    def fake_search_documents(query, n_results):
        assert query == "What is satellite safe mode?"
        assert n_results == 3

        return [
            {
                "text": "Safe mode protects a satellite during anomalies.",
                "source": "satellite_health.md",
                "chunk_index": 0,
                "distance": 0.15,
            }
        ]

    def fake_generate_grounded_answer(query, chunks):
        assert query == "What is satellite safe mode?"
        assert len(chunks) == 1

        return {
            "answer": (
                "Safe mode protects the satellite during anomalies. [S1]"
            ),
            "sources": [
                {
                    "id": "S1",
                    "source": "satellite_health.md",
                    "chunk_index": 0,
                }
            ],
        }

    monkeypatch.setattr(
        "app.main.search_documents", fake_search_documents
    )
    monkeypatch.setattr(
        "app.main.generate_grounded_answer",
        fake_generate_grounded_answer,
    )

    response = client.post(
        "/answer",
        json={
            "query": "What is satellite safe mode?",
            "top_k": 3,
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert set(data.keys()) == {
        "query",
        "answer",
        "sources",
        "source_count",
    }

    assert isinstance(data["query"], str)
    assert isinstance(data["answer"], str)
    assert isinstance(data["sources"], list)
    assert isinstance(data["source_count"], int)

    assert set(data["sources"][0].keys()) == {
        "id",
        "source",
        "chunk_index",
    }
    assert data["query"] == "What is satellite safe mode?"
    assert "[S1]" in data["answer"]
    assert data["source_count"] == 1
    assert data["sources"][0]["id"] == "S1"
    assert data["sources"][0]["source"] == "satellite_health.md"
    assert data["sources"][0]["chunk_index"] == 0


def test_answer_rejects_empty_query():
    response = client.post(
        "/answer",
        json={"query": "", "top_k": 3},
    )

    assert response.status_code == 422


def test_answer_handles_retrieval_failure(monkeypatch):
    def fake_search_documents(query, n_results):
        raise RuntimeError("Simulated retrieval failure")

    monkeypatch.setattr(
        "app.main.search_documents", fake_search_documents
    )

    response = client.post(
        "/answer",
        json={
            "query": "What is satellite safe mode?",
            "top_k": 3,
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == (
        "Could not retrieve supporting documents."
    )


def test_answer_handles_generation_failure(monkeypatch):
    def fake_search_documents(query, n_results):
        return [
            {
                "text": "Safe mode protects a satellite.",
                "source": "satellite_health.md",
                "chunk_index": 0,
                "distance": 0.15,
            }
        ]

    def fake_generate_grounded_answer(query, chunks):
        raise RuntimeError("Simulated Ollama failure")

    monkeypatch.setattr(
        "app.main.search_documents", fake_search_documents
    )
    monkeypatch.setattr(
        "app.main.generate_grounded_answer",
        fake_generate_grounded_answer,
    )

    response = client.post(
        "/answer",
        json={
            "query": "What is satellite safe mode?",
            "top_k": 3,
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == (
        "Answer generation failed. Check the FastAPI server logs."
    )
