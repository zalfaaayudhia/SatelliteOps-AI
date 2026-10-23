
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.llm import (
    LLMConfigurationError,
    generate_grounded_answer,
)
from app.vector_store import search_documents


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="SatelliteOps AI",
    description="AI-powered satellite operations assistant",
    version="0.4.0",
)


# -------------------------
# Request and response models
# -------------------------

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


class AnswerRequest(BaseModel):
    query: str = Field(
        min_length=1,
        max_length=2000,
        description="Question about satellite operations",
    )
    top_k: int = Field(default=3, ge=1, le=10)


class AnswerSource(BaseModel):
    id: str
    source: str
    chunk_index: int


class AnswerResponse(BaseModel):
    query: str
    answer: str
    sources: list[AnswerSource]
    source_count: int


# -------------------------
# Health check
# -------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "python-ai",
    }


# -------------------------
# Semantic retrieval API
# -------------------------

@app.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: RetrieveRequest):
    """Retrieve relevant chunks from the satellite operations knowledge base."""

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

    except HTTPException:
        raise

    except ValueError as exc:
        logger.warning("Invalid retrieval request: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        logger.exception("Document retrieval failed")
        raise HTTPException(
            status_code=500,
            detail="Document retrieval failed. Check the server logs.",
        ) from exc


# -------------------------
# Grounded LLM answer API
# -------------------------

@app.post("/answer", response_model=AnswerResponse)
def answer_question(request: AnswerRequest):
    """Generate an answer grounded in retrieved document chunks."""

    if not request.query.strip():
        raise HTTPException(
            status_code=422,
            detail="Query must not be empty or whitespace only",
        )

    # Step 1: Retrieve supporting document chunks.
    try:
        chunks = search_documents(
            query=request.query,
            n_results=request.top_k,
        )

    except ValueError as exc:
        logger.warning("Retrieval input error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Could not process the retrieval request.",
        ) from exc

    except Exception as exc:
        logger.exception("Retrieval failed during answer generation")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve supporting documents.",
        ) from exc

    # Step 2: Generate an answer using the retrieved context.
    try:
        result = generate_grounded_answer(
            query=request.query,
            chunks=chunks,
        )

        return AnswerResponse(
            query=request.query,
            answer=result["answer"],
            sources=[
                AnswerSource(**source)
                for source in result["sources"]
            ],
            source_count=len(result["sources"]),
        )

    except LLMConfigurationError as exc:
        logger.error("LLM configuration error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        logger.exception("Invalid input or retrieval result")
        raise HTTPException(
            status_code=422,
            detail="Could not process the retrieved information.",
        ) from exc

    except Exception as exc:
        # This covers local Ollama errors as well as unexpected failures.
        # It intentionally does not assume the provider is OpenAI.
        logger.exception("Unexpected answer generation failure")
        raise HTTPException(
            status_code=502,
            detail=(
                "Answer generation failed. "
                "Check the FastAPI server logs."
            ),
        ) from exc
