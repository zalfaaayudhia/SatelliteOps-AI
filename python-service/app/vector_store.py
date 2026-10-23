
import json
from pathlib import Path

import chromadb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_FILE = PROJECT_ROOT / "data" / "processed" / "chunks.jsonl"
VECTOR_DB_DIR = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "satellite_operations"


def get_collection():
    """Open or create the persistent vector collection."""
    client = chromadb.PersistentClient(path=str(VECTOR_DB_DIR))

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    return collection


def load_chunks(chunks_file: Path = CHUNKS_FILE) -> list[dict]:
    """Load the previously generated JSONL chunks."""
    if not chunks_file.exists():
        raise FileNotFoundError(
            f"Chunks file not found: {chunks_file}. "
            "Run python -m app.ingestion first."
        )

    chunks = []

    with chunks_file.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number}"
                ) from exc

            required_fields = {
                "chunk_id",
                "source",
                "chunk_index",
                "text",
            }

            if not required_fields.issubset(chunk):
                raise ValueError(
                    f"Missing required fields on line {line_number}"
                )

            if not chunk["text"].strip():
                continue

            chunks.append(chunk)

    return chunks


def index_chunks() -> int:
    """Embed chunks and store them in ChromaDB."""
    chunks = load_chunks()

    if not chunks:
        raise ValueError("No valid document chunks to index.")

    collection = get_collection()

    # Chroma's default embedding function generates embeddings locally.
    # upsert makes rerunning the indexing step safe for existing IDs.
    collection.upsert(
        ids=[chunk["chunk_id"] for chunk in chunks],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[
            {
                "source": chunk["source"],
                "chunk_index": chunk["chunk_index"],
            }
            for chunk in chunks
        ],
    )

    return collection.count()


def search_documents(query: str, n_results: int = 3) -> list[dict]:
    """Retrieve chunks most similar to a query."""
    if not query.strip():
        raise ValueError("Query must not be empty.")

    if n_results < 1:
        raise ValueError("n_results must be at least 1.")

    collection = get_collection()

    if collection.count() == 0:
        raise ValueError(
            "Vector collection is empty. Run indexing first."
        )

    results = collection.query(
        query_texts=[query],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    matches = []

    for i, document in enumerate(results["documents"][0]):
        matches.append(
            {
                "text": document,
                "source": results["metadatas"][0][i]["source"],
                "chunk_index": results["metadatas"][0][i]["chunk_index"],
                "distance": results["distances"][0][i],
            }
        )

    return matches


if __name__ == "__main__":
    total = index_chunks()

    print(f"Vector database: {VECTOR_DB_DIR}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Indexed chunks: {total}")

    query = "How should an engineer investigate a satellite anomaly?"
    print(f"\nTest query: {query}")

    for result in search_documents(query):
        print(f"\nSource: {result['source']}")
        print(f"Distance: {result['distance']:.4f}")
        print(f"Text: {result['text'][:200]}...")
