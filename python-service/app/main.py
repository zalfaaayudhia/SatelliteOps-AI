
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.vector_store import search_documents, get_collection


app = FastAPI(
    title="SatelliteOps AI",
    description="AI-powered satellite operations assistant",
    version="0.2.0",
)


class RetrieveRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=2000,
        description="Question to search for in the knowledge base",
    )
    top_k: int = Field(default=3, ge=1, le=10)


class RetrievedChunk(BaseModel):
    text: str
    source: str
    chunk_index: int
    distance: float


class RetrieveResponse(BaseModel):
    query: str
    results: list[RetrievedChunk]
    result_count: int


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "python-ai",
    }


@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: RetrieveRequest):
    """Retrieve relevant knowledge-base chunks for a question."""
    if not request.query.strip():
        raise HTTPException(
            status_code=422,
            detail="Query must not be empty or whitespace only",
        )

    try:
        results = search_documents(
            query=request.query,
            n_results=request.top_k,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        # Log the exception in production; don't expose internal details.
        raise HTTPException(
            status_code=500,
            detail="Document retrieval failed",
        ) from exc

    return RetrieveResponse(
        query=request.query,
        results=[
            RetrievedChunk(
                text=result["text"],
                source=result["source"],
                chunk_index=result["chunk_index"],
                distance=result["distance"],
            )
            for result in results
        ],
        result_count=len(results),
    )
