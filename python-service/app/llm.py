
import os
from openai import OpenAI

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434/v1",
)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# Ollama runs locally, so this is a placeholder rather than an
# actual OpenAI API key.
client = OpenAI(
    base_url=OLLAMA_BASE_URL,
    api_key="ollama",
    timeout=120.0,
    max_retries=0,
)


class LLMConfigurationError(Exception):
    """Raised when the local LLM configuration is invalid."""


def generate_grounded_answer(query: str, chunks: list[dict]) -> dict:
    """
    Generate an answer using retrieved document chunks.

    Returns the existing contract:
    {
        "answer": "...",
        "sources": [
            {
                "id": "S1",
                "source": "...",
                "chunk_index": 0
            }
        ]
    }
    """

    if not query or not query.strip():
        raise ValueError("Query must not be empty.")

    if not chunks:
        return {
            "answer": (
                "I could not find relevant information in the available "
                "satellite operations documents to answer this question."
            ),
            "sources": [],
        }

    source_entries = []
    context_parts = []

    for index, chunk in enumerate(chunks, start=1):
        source_id = f"S{index}"
        source_name = str(chunk.get("source", "unknown"))
        chunk_index = chunk.get("chunk_index", 0)
        chunk_text = str(chunk.get("text", "")).strip()

        source_entries.append({
            "id": source_id,
            "source": source_name,
            "chunk_index": chunk_index,
        })

        if chunk_text:
            context_parts.append(
                f"[{source_id}]\n"
                f"Source: {source_name}\n"
                f"Chunk index: {chunk_index}\n"
                f"Content:\n{chunk_text}"
            )

    if not context_parts:
        return {
            "answer": (
                "I could not find usable document content to answer "
                "this question."
            ),
            "sources": [],
        }

    context = "\n\n---\n\n".join(context_parts)

    instructions = """
You are SatelliteOps AI, an assistant for satellite operations.

Answer the user's question using ONLY the supplied document excerpts.

Rules:
1. Do not invent facts or use unsupported outside knowledge.
2. Cite supporting excerpts using their exact IDs, such as [S1] or [S2].
3. If the excerpts do not contain enough information, say so clearly.
4. Distinguish documented facts from uncertainty.
5. Give practical, concise answers with numbered steps when appropriate.
6. Never invent a source ID.
"""

    try:
        response = client.chat.completions.create(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": instructions,
                },
                {
                    "role": "user",
                    "content": (
                        f"DOCUMENT EXCERPTS:\n{context}\n\n"
                        f"QUESTION:\n{query}"
                    ),
                },
            ],
            temperature=0.1,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Local Ollama generation failed: {exc}"
        ) from exc

    answer = response.choices[0].message.content

    if not answer:
        answer = (
            "The model returned an empty answer. "
            "Please try rephrasing the question."
        )

    return {
        "answer": answer.strip(),
        "sources": source_entries,
    }
